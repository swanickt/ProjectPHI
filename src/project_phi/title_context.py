"""Title-context false-positive vetoes for pyDeid name spans.

pyDeid can label lower-case clinical action words as names after title tokens
such as ``Dr.``. These helpers do not detect new PHI. They only inspect
pyDeid-emitted spans during reconstruction and preserve a narrow set of
lower-case action words when the title context strongly suggests a grammar
false positive rather than a real name.
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources
from typing import Any

from .models import PHISpan


_TITLE_DERIVED_NAME_TYPE_PATTERNS = (
    "Name (STitle)",
    "Last Name (STitle)",
    "First Name (STitle)",
    "Last Name (Titles)",
    "First Name (Titles)",
)

_CUSTOM_NAME_TYPE_MARKERS = (
    "Custom Patient",
    "Custom Doctor",
)

_PYDEID_NAME_WORDLIST_FILES = (
    "all_first_names.txt",
    "all_last_names.txt",
    "doctor_first_names.txt",
    "doctor_last_names.txt",
    "female_names_ambig.txt",
    "female_names_popular_v2.txt",
    "female_names_unambig_v2.txt",
    "last_names_ambig.txt",
    "last_names_popular_v2.txt",
    "last_names_unambig_v2.txt",
    "male_names_ambig.txt",
    "male_names_popular_v2.txt",
    "male_names_unambig_v2.txt",
)

_CLINICAL_ACTION_WORDS = frozenset(
    """
    acknowledge acknowledged acknowledges acknowledging
    administer administered administering administers
    admit admitted admitting admits
    advise advised advises advising
    arrange arranged arranges arranging
    assess assessed assesses assessing
    attend attended attending attends
    attempt attempted attempting attempts
    biopsy biopsied biopsies biopsying
    book booked booking
    call called calls calling
    characterize characterized characterizes characterizing
    check checked checks checking
    clarify clarified clarifies clarifying
    classify classified classifies classifying
    collect collected collecting collects
    compare compared compares comparing
    complete completed completes completing
    confirm confirmed confirms confirming
    consider considered considers considering
    consult consulted consults consulting
    contact contacted contacts contacting
    continue continued continues continuing
    control controlled controlling controls
    coordinate coordinated coordinates coordinating
    correlate correlated correlates correlating
    counsel counseled counseling counselled counsels counselling
    decline declined declines declining
    defer deferred deferring defers
    demonstrate demonstrated demonstrates demonstrating
    deny denied denies denying
    depict depicted depicting depicts
    describe described describes describing
    detect detected detecting detects
    develop developed developing develops
    diagnose diagnosed diagnoses diagnosing
    differentiate differentiated differentiates differentiating
    discharge discharged discharges discharging
    discuss discussed discusses discussing
    document documented documents documenting
    educate educated educates educating
    embed embedded embedding embeds
    endorse endorsed endorses endorsing
    enlarge enlarged enlarges enlarging
    eradicate eradicated eradicates eradicating
    escalate escalated escalates escalating
    evaluate evaluated evaluates evaluating
    evolve evolved evolves evolving
    examine examined examines examining
    exclude excluded excludes excluding
    explain explained explains explaining
    favor favored favoring favors
    follow followed following follows
    grade graded grades grading
    grow growing grows
    hold held holding holds
    identify identified identifies identifying
    image imaged images imaging
    improve improved improves improving
    indicate indicated indicates indicating
    initiate initiated initiates initiating
    instruct instructed instructs instructing
    interpret interpreted interprets interpreting
    involve involved involves involving
    irradiate irradiated irradiates irradiating
    localize localized localizes localizing
    lump lumped lumping lumps
    measure measured measures measuring
    metastasize metastasized metastasizes metastasizing
    monitor monitored monitors monitoring
    note noted notes noting
    observe observed observes observing
    obtain obtained obtaining obtains
    order ordered ordering orders
    palpate palpated palpates palpating
    perform performed performing performs
    persist persisted persisting persists
    plan planned planning plans
    prescribe prescribed prescribes prescribing
    present presented presenting presents
    progress progressed progresses progressing
    project projected projecting projects
    radiate radiated radiates radiating
    receive received receives receiving
    recommend recommended recommending recommends
    reconcile reconciled reconciles reconciling
    record recorded recording
    recur recurred recurring recurs
    reduce reduced reduces reducing
    refer referred refers referring
    refill refilled refilling refills
    regress regressed regresses regressing
    relapse relapsed relapses relapsing
    remain remained remaining remains
    repeat repeated repeating repeats
    report reported reports reporting
    request requested requests requesting
    resolve resolved resolves resolving
    respond responded responding responds
    result resulted resulting results
    return returned returning returns
    review reviewed reviews reviewing
    sample sampled samples sampling
    schedule scheduled schedules scheduling
    screen screened screening screens
    section sectioned sectioning sections
    send sending sends sent
    show showed showing shows
    sign signed signing signs
    speak speaking speaks spoke
    stabilize stabilized stabilizes stabilizing
    stage staged stages staging
    start started starting starts
    stop stopped stopping stops
    submit submitted submitting submits
    suggest suggested suggesting suggests
    target targeted targeting targets
    tolerate tolerated tolerates tolerating
    transition transitioned transitioning transitions
    treat treated treating treats
    undergo undergoes undergoing underwent
    update updated updates updating
    verify verified verifies verifying
    visualize visualized visualizes visualizing
    warrant warranted warranting warrants
    witness witnessed witnesses witnessing
    worsen worsened worsening worsens
    """.split()
)

_SURROUNDING_PUNCTUATION = " \t\r\n.,;:)]}([{\"'"


def _normalize_action_word(text: str) -> str:
    """Normalize a single action-word candidate for exact matching."""
    return " ".join(str(text).strip(_SURROUNDING_PUNCTUATION).casefold().split())


def _title_context_action_word_match(
    span: PHISpan,
    *,
    original_text: str,
    spans: list[PHISpan],
    patient_name_alias_profile: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    """Return policy metadata when a title-derived name span is an action word.

    The rule is intentionally conjunctive: an action word is preserved only
    when it is lower-case in the source text, appears in a narrow title context,
    is not an explicit alias/custom name, and is absent from pyDeid name lists.
    """
    if span.label != "NAME":
        return None
    if not _is_title_derived_name_span(span):
        return None
    if _has_custom_name_type(span):
        return None
    if not _is_single_lowercase_alpha_token(span.text):
        return None

    normalized_word = _normalize_action_word(span.text)
    if normalized_word not in _CLINICAL_ACTION_WORDS:
        return None
    if _is_patient_alias_component(normalized_word, patient_name_alias_profile):
        return None
    if _is_known_pydeid_name_word(normalized_word):
        return None
    if not _has_title_context(span, original_text=original_text, spans=spans):
        return None

    return {
        "project_title_context_policy": "title_context_action_word_exact_match",
        "project_title_context_trigger": "strict_title_name_heuristic",
        "project_title_context_word": normalized_word,
    }


def _title_context_action_word_metadata(match: dict[str, str]) -> dict[str, str]:
    """Return audit/reconstruction metadata for a matched action-word veto."""
    return dict(match)


def _is_single_lowercase_alpha_token(text: str) -> bool:
    """Return true for one lower-case alphabetic source token."""
    token = str(text).strip(_SURROUNDING_PUNCTUATION)
    return bool(token) and token.isalpha() and token.islower()


def _is_title_derived_name_span(span: PHISpan) -> bool:
    """Return true when pyDeid's type labels came from title-name heuristics."""
    return any(
        title_type in pydeid_type
        for pydeid_type in span.pydeid_types
        for title_type in _TITLE_DERIVED_NAME_TYPE_PATTERNS
    )


def _has_custom_name_type(span: PHISpan) -> bool:
    """Return true when a span came from explicit custom name-list hooks."""
    return any(
        marker in pydeid_type
        for pydeid_type in span.pydeid_types
        for marker in _CUSTOM_NAME_TYPE_MARKERS
    )


def _is_patient_alias_component(
    normalized_word: str,
    patient_name_alias_profile: dict[str, Any] | None,
) -> bool:
    """Return true when the candidate is an explicit patient alias component."""
    if not patient_name_alias_profile:
        return False
    alias_sets = (
        "given_names",
        "family_names_explicit",
        "family_names_from_full",
    )
    return any(normalized_word in patient_name_alias_profile.get(key, set()) for key in alias_sets)


def _has_title_context(
    span: PHISpan,
    *,
    original_text: str,
    spans: list[PHISpan],
) -> bool:
    """Return true for `Dr. <candidate>` or `Dr. <span> <candidate>` contexts."""
    if _text_before_ends_with_title(original_text[: span.start]):
        return True

    previous_span = _previous_adjacent_span(span, spans, original_text)
    if previous_span is None:
        return False
    if previous_span.label != "NAME" or not _is_title_derived_name_span(previous_span):
        return False
    return _text_before_ends_with_title(original_text[: previous_span.start])


def _previous_adjacent_span(
    span: PHISpan,
    spans: list[PHISpan],
    original_text: str,
) -> PHISpan | None:
    """Return the nearest previous span when only whitespace separates spans."""
    previous_spans = [candidate for candidate in spans if candidate.end <= span.start]
    if not previous_spans:
        return None
    previous_span = max(previous_spans, key=lambda candidate: candidate.end)
    if original_text[previous_span.end : span.start].strip():
        return None
    return previous_span


def _text_before_ends_with_title(text_before: str) -> bool:
    """Return true when preceding text ends with a short doctor title."""
    return bool(re.search(r"(?:^|[^A-Za-z])(?:the\s+)?dr\.?\s*$", text_before, re.IGNORECASE))


def _is_known_pydeid_name_word(normalized_word: str) -> bool:
    """Return true when local pyDeid name lists already contain the candidate.

    If the pyDeid lists cannot be read, fail conservative by treating the word
    as known. The action-word veto should not run without this safety brake.
    """
    name_words = _load_pydeid_name_words()
    if name_words is None:
        return True
    return normalized_word in name_words


@lru_cache(maxsize=1)
def _load_pydeid_name_words() -> frozenset[str] | None:
    """Load pyDeid name-list words at runtime without copying them into ProjectPHI."""
    try:
        wordlist_root = resources.files("pyDeid.wordlists")
    except (ImportError, ModuleNotFoundError):
        return None

    words: set[str] = set()
    try:
        for filename in _PYDEID_NAME_WORDLIST_FILES:
            path = wordlist_root / filename
            with path.open(encoding="utf-8", errors="ignore") as handle:
                words.update(
                    _normalize_action_word(line)
                    for line in handle
                    if _normalize_action_word(line)
                )
    except (FileNotFoundError, OSError):
        return None
    return frozenset(words)
