"""Project-stable replacement reconstruction from original-note offsets.

Reconstruction is used when ProjectPHI needs final replacements that may differ
from pyDeid's initial surrogate text, such as stable date shifts, stable patient
aliases, or protected clinical-term preservation.

This module rebuilds the final note from the original note plus normalized
`PHISpan` offsets. It does not edit pyDeid's already-de-identified output string,
because project replacements may have different lengths and can invalidate
pyDeid-output offsets.

Offset convention:
- `PHISpan.start` / `PHISpan.end` remain offsets in the original note.
- `pydeid_surrogate_start` / `pydeid_surrogate_end`, when present, refer to
  pyDeid's initially de-identified output.
- `project_replacement_start` / `project_replacement_end` are added here and
  refer to the final ProjectPHI output text.

Replacement priority:
1. Preserve protected clinical terms when a pyDeid span exactly matches one, or
   when a configured risky component appears inside an approved clinical phrase.
2. Preserve narrow clinical abbreviation false positives such as `PMHx`.
3. Apply stable date shifting/preservation/fallback when date shifting is enabled.
4. Apply stable patient-name aliases when name replacement is enabled.
5. Preserve narrow ordinary-token false positives such as articles/pronouns.
6. Preserve narrow title-context action-word false positives.
7. Fall back to pyDeid's replacement, or `<PHI>` if pyDeid did not provide one.

Examples:
    Original:
        "Jane Smith had imaging on January 5, 2024."

    With patient-name identity `Alex Bennett` and date offset +10:
        "Alex Bennett had imaging on January 15, 2024."

    Original:
        "BI-RADS 2 was documented on January 2024."

    If `BI-RADS 2` is a protected term and date offset is +25:
        "BI-RADS 2 was documented on February 2024."

Safety:
- overlapping spans fail closed with `ValueError`;
- raw original text is copied only outside detected spans;
- replacement offsets are recorded in project-final coordinates.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .date_shift import (
    _date_shift_metadata_for_month_year_span,
    _date_shift_policy_for_full_date_span,
    _is_date_like_span,
    _is_holiday_or_season_span,
    _is_parseable_month_year_span,
    _is_parseable_full_date_span,
    _is_score_or_fraction_date_span,
    _is_time_span,
    _is_year_only_span,
    _score_or_fraction_date_metadata,
    _shift_full_date_span,
    _shift_month_year_span,
)
from .models import PHISpan
from .patient_names import _name_policy_metadata, _project_patient_name_replacement
from .protected_terms import _protected_term_match, _protected_term_metadata
from .title_context import (
    _title_context_action_word_match,
    _title_context_action_word_metadata,
)

_ORDINARY_ARTICLE_PRONOUN_TOKENS = {
    "a",
    "an",
    "he",
    "her",
    "his",
    "she",
    "the",
}

_INITIAL_CONTEXT_PREFIXES = (
    "case",
    "control",
    "dr",
    "doctor",
    "family",
    "mr",
    "mrs",
    "ms",
    "patient",
    "participant",
    "subject",
)

_NH_CONTEXT_AFTER = (
    " resident",
    " patient",
    " facility",
    " placement",
    " transfer",
    " staff",
)

_NH_CONTEXT_BEFORE = (
    " from ",
    " at ",
    " in ",
    " to ",
    " transferred from ",
    " sent from ",
    " discharged to ",
)


def _reconstruct_with_stable_dates(
    original_text: str,
    spans: list[PHISpan],
    *,
    date_shift_offset: int,
    date_shift_days: int,
) -> tuple[str, list[PHISpan], list[str]]:
    """Reconstruct final text with stable date shifting only.

    This is a compatibility wrapper around
    `_reconstruct_with_project_replacements(...)` for callers that only enable
    date-shift behavior.

    Args:
        original_text: Full original note text.
        spans: Normalized pyDeid spans with original-note offsets.
        date_shift_offset: Patient-specific day offset to apply to parseable dates.
        date_shift_days: Configured inclusive shift range, recorded for audit.

    Returns:
        `(deidentified_text, final_spans, warnings)`.
    """
    return _reconstruct_with_project_replacements(
        original_text,
        spans,
        date_shift_offset=date_shift_offset,
        date_shift_days=date_shift_days,
    )


def _reconstruct_with_project_replacements(
    original_text: str,
    spans: list[PHISpan],
    *,
    date_shift_offset: int | None = None,
    date_shift_days: int | None = None,
    patient_name_alias_profile: dict[str, Any] | None = None,
    patient_name_identity: dict[str, str] | None = None,
    protected_terms_profile: dict[str, Any] | None = None,
) -> tuple[str, list[PHISpan], list[str]]:
    """Rebuild final note text from original text and normalized spans.

    This function walks through the original note from left to right, copies
    unchanged text between spans, and inserts one selected replacement for each
    span. It also records final replacement offsets in each returned span's
    metadata.

    Args:
        original_text: Full original note text.
        spans: Normalized pyDeid spans. Their `start` and `end` offsets must
            refer to `original_text`.
        date_shift_offset: Optional patient-specific day offset. When provided,
            date-like spans receive stable date policy.
        date_shift_days: Optional configured inclusive date-shift range, recorded
            in audit metadata when date shifting is enabled.
        patient_name_alias_profile: Optional explicit patient-alias profile used
            to decide which pyDeid name spans receive stable patient-name
            surrogates.
        patient_name_identity: Optional deterministic fake patient identity.
        protected_terms_profile: Optional protected-term profile used to preserve
            clinical terms that pyDeid emitted as spans.

    Returns:
        A tuple `(final_text, final_spans, warnings)`:
        - `final_text`: reconstructed de-identified note text;
        - `final_spans`: copies of input spans with final replacement metadata;
        - `warnings`: sanitized reconstruction warnings.

    Raises:
        ValueError: If pyDeid spans overlap, because reconstruction cannot safely
            decide which original text to copy or replace.

    Example:
        Original text:
            "Jane Smith visited on January 5, 2024."

        Input spans:
            - `Jane Smith`, label `NAME`, offsets 0:10
            - `January 5, 2024`, label `DATE`, offsets 22:37

        With stable patient-name and date-shift policies enabled, this function
        copies `" visited on "` unchanged and replaces only the two span ranges.
    """
    final_parts: list[str] = []
    final_spans: list[PHISpan] = []
    warnings: list[str] = []
    cursor = 0
    final_offset = 0
    sorted_spans = sorted(spans, key=lambda item: (item.start, item.end))

    for span in sorted_spans:
        if span.start < cursor:
            # Fail closed. Overlapping spans make it unclear which original text
            # should be copied or replaced; silently continuing could leak PHI.
            raise ValueError("Overlapping pyDeid spans cannot be safely reconstructed.")

        unchanged_text = original_text[cursor : span.start]
        final_parts.append(unchanged_text)
        final_offset += len(unchanged_text)

        replacement_info = _project_replacement_for_span(
            span,
            all_spans=sorted_spans,
            date_shift_offset=date_shift_offset,
            original_text=original_text,
            patient_name_alias_profile=patient_name_alias_profile,
            patient_name_identity=patient_name_identity,
            protected_terms_profile=protected_terms_profile,
        )
        replacement_text, replacement_source, policy, policy_metadata = replacement_info
        if policy == "unparseable_date_placeholder":
            warnings.append("Unparseable pyDeid date span replaced with <DATE>.")
        replacement_start = final_offset
        final_parts.append(replacement_text)
        final_offset += len(replacement_text)
        replacement_end = final_offset

        metadata = dict(span.metadata)
        # These offsets point into the final ProjectPHI output text. They are
        # separate from original-note offsets and pyDeid-output surrogate offsets.
        metadata.update(
            {
                "replacement_source": replacement_source,
                "project_replacement": replacement_text,
                "project_replacement_start": replacement_start,
                "project_replacement_end": replacement_end,
            }
        )
        if date_shift_offset is not None:
            metadata["project_date_shift_range_days"] = date_shift_days
            metadata["project_date_shift_policy"] = policy
        if replacement_source == "project_stable_date_shift" and date_shift_offset is not None:
            metadata["project_date_shift_days"] = date_shift_offset
        if patient_name_alias_profile is not None and span.label == "NAME":
            metadata.update(_name_policy_metadata(replacement_source, policy))
        metadata.update(policy_metadata)

        final_spans.append(
            replace(
                span,
                action="replaced" if replacement_text != span.text else "preserved",
                replacement=replacement_text,
                metadata=metadata,
            )
        )
        cursor = span.end

    trailing_text = original_text[cursor:]
    final_parts.append(trailing_text)
    return "".join(final_parts), final_spans, warnings


def _project_replacement_for_span(
    span: PHISpan,
    *,
    all_spans: list[PHISpan] | None = None,
    date_shift_offset: int | None = None,
    original_text: str = "",
    patient_name_alias_profile: dict[str, Any] | None = None,
    patient_name_identity: dict[str, str] | None = None,
    protected_terms_profile: dict[str, Any] | None = None,
) -> tuple[str, str, str, dict[str, Any]]:
    """Choose final replacement text and policy metadata for one span.

    Priority order is intentional:

    1. Protected clinical-term veto:
       preserve the original span text when pyDeid emitted a span that exactly
       matches a protected clinical term, or when a risky component is inside a
       configured clinical tool/scale phrase.

    2. Clinical abbreviation veto:
       preserve selected clinical abbreviations that pyDeid emits as facility
       acronyms inside longer clinical shorthand.

    3. Stable date policy:
       shift parseable full dates and month/year spans; preserve times,
       score/fraction notation, year-only spans, holidays, and seasons; replace
       unparseable date-like spans with `<DATE>`.

    4. Stable patient-name policy:
       replace explicit patient aliases with the deterministic fake patient
       identity.

    5. Ordinary-token veto:
       preserve selected articles, pronouns, and clinical shorthand that pyDeid
       emitted as very short name spans when context supports a non-name read.

    6. Title-context action-word veto:
       preserve narrow clinical action words that pyDeid emitted as
       title-derived name spans in `Dr.` contexts. Lower-case words use the
       base rule; capitalized words require following clinical-object context.

    7. pyDeid fallback:
       use pyDeid's replacement, or `<PHI>` if no replacement is available.

    Args:
        span: Current normalized pyDeid span.
        all_spans: Full normalized pyDeid span list for title-context checks.
        date_shift_offset: Optional patient-specific day offset. Date policy is
            enabled only when this is not `None`.
        original_text: Full original note text, used for split patient-alias
            context checks.
        patient_name_alias_profile: Optional explicit patient-alias profile.
        patient_name_identity: Optional deterministic fake patient identity.
        protected_terms_profile: Optional protected-term profile.

    Returns:
        `(replacement_text, replacement_source, policy, policy_metadata)`.

        Examples:
        - protected term: `("BI-RADS 2", "project_protected_clinical_term",
          "exact_normalized_span_match", {...})`
        - shifted date: `("January 15, 2024", "project_stable_date_shift",
          "shifted_natural_language_full_date", {})`
        - known patient alias: `("Alex Bennett", "project_stable_patient_name",
          "full", {})`
        - title-context action word: `("reviewed",
          "project_title_context_action_word_veto",
          "title_context_action_word_exact_match", {...})`
        - unknown name: `("[**Name**]", "pyDeid", "unknown_name_pydeid", {})`

    Notes:
        This function does not mutate `span`.
    """
    protected_match = _protected_term_match(span, protected_terms_profile, original_text)
    if protected_match is not None:
        return (
            span.text,
            "project_protected_clinical_term",
            "exact_normalized_span_match",
            _protected_term_metadata(protected_match),
        )

    clinical_abbreviation_match = _clinical_abbreviation_veto_metadata(span, original_text)
    if clinical_abbreviation_match is not None:
        return (
            span.text,
            "project_clinical_abbreviation_veto",
            clinical_abbreviation_match["project_clinical_abbreviation_policy"],
            clinical_abbreviation_match,
        )

    # Date policy: shift parseable dates, preserve date-like spans that should
    # not receive day-level shifting, and use a safe placeholder for unparseable
    # date-like spans.
    if date_shift_offset is not None and _is_score_or_fraction_date_span(span, original_text):
        return (
            span.text,
            "preserved",
            "preserved_score_or_fraction",
            _score_or_fraction_date_metadata(),
        )

    if date_shift_offset is not None and _is_parseable_full_date_span(span):
        shifted_text = _shift_full_date_span(span, date_shift_offset)
        if shifted_text is not None:
            return (
                shifted_text,
                "project_stable_date_shift",
                _date_shift_policy_for_full_date_span(span),
                {},
            )

    if date_shift_offset is not None and _is_parseable_month_year_span(span):
        shifted_text = _shift_month_year_span(span, date_shift_offset)
        if shifted_text is not None:
            return (
                shifted_text,
                "project_stable_date_shift",
                "shifted_month_year",
                _date_shift_metadata_for_month_year_span(),
            )

    if date_shift_offset is not None and _is_time_span(span):
        return span.text, "preserved", "preserved_time", {}
    if date_shift_offset is not None and _is_year_only_span(span):
        return span.text, "preserved", "preserved_year_only", {}
    if date_shift_offset is not None and _is_holiday_or_season_span(span):
        return span.text, "preserved", "preserved_holiday_or_season", {}
    if date_shift_offset is not None and _is_date_like_span(span):
        return "<DATE>", "project_stable_date_shift", "unparseable_date_placeholder", {}

    # Patient-name policy: only explicit patient aliases receive the stable fake
    # patient identity. Unknown names remain pyDeid replacements.
    if patient_name_alias_profile is not None and patient_name_identity is not None and span.label == "NAME":
        name_replacement = _project_patient_name_replacement(
            span,
            original_text=original_text,
            alias_profile=patient_name_alias_profile,
            identity=patient_name_identity,
        )
        if name_replacement is not None:
            replacement_text, match_type = name_replacement
            return replacement_text, "project_stable_patient_name", match_type, {}

    ordinary_token_match = _ordinary_token_veto_metadata(span, original_text)
    if ordinary_token_match is not None:
        return (
            span.text,
            "project_ordinary_token_veto",
            ordinary_token_match["project_ordinary_token_policy"],
            ordinary_token_match,
        )

    title_context_match = _title_context_action_word_match(
        span,
        original_text=original_text,
        spans=all_spans or [],
        patient_name_alias_profile=patient_name_alias_profile,
    )
    if title_context_match is not None:
        return (
            span.text,
            "project_title_context_action_word_veto",
            title_context_match["project_title_context_policy"],
            _title_context_action_word_metadata(title_context_match),
        )

    if patient_name_alias_profile is not None and patient_name_identity is not None and span.label == "NAME":
        return span.replacement or "<PHI>", "pyDeid", "unknown_name_pydeid", {}

    # Final fallback for all other spans.
    return span.replacement or "<PHI>", "pyDeid", "pydeid_replacement", {}


def _ordinary_token_veto_metadata(
    span: PHISpan,
    original_text: str,
) -> dict[str, str] | None:
    """Return metadata for very narrow common-token name false positives.

    This is not a name detector. It only preserves selected pyDeid-emitted
    `NAME` spans whose whole text is a common article/pronoun or the observed
    nursing-home shorthand `NH`, and only when simple local guards suggest that
    preserving the token is safer than replacing it.
    """
    if span.label != "NAME":
        return None

    token = span.text
    normalized = token.casefold()
    if normalized in _ORDINARY_ARTICLE_PRONOUN_TOKENS:
        if _looks_like_initial_or_case_label_context(span, original_text):
            return None
        return {
            "project_ordinary_token_policy": "preserved_pronoun_or_article",
            "project_ordinary_token": token,
            "project_ordinary_token_category": "pronoun_or_article",
        }

    if token == "NH" and _has_nursing_home_context(span, original_text):
        return {
            "project_ordinary_token_policy": "preserved_clinical_shorthand",
            "project_ordinary_token": token,
            "project_ordinary_token_category": "nursing_home",
        }

    return None


def _clinical_abbreviation_veto_metadata(
    span: PHISpan,
    original_text: str,
) -> dict[str, str] | None:
    """Return metadata when a pyDeid facility acronym is clinical shorthand.

    pyDeid's hospital acronym list includes `PMH`. Its acronym matcher can emit
    `PMH` inside `PMHx`, which is common shorthand for past medical history.
    This project veto is intentionally narrow and span-local: it only preserves
    the pyDeid-emitted `PMH` span when the next source character is `x`/`X`.
    """
    if span.text.upper() != "PMH":
        return None
    if "site acronym" not in " ".join(span.pydeid_types or []).lower():
        return None
    if span.end >= len(original_text) or original_text[span.end] not in {"x", "X"}:
        return None

    return {
        "project_clinical_abbreviation_policy": "preserved_pmhx_site_acronym_overlap",
        "project_clinical_abbreviation": original_text[span.start : span.end + 1],
    }


def _looks_like_initial_or_case_label_context(
    span: PHISpan,
    original_text: str,
) -> bool:
    """Return true when a short token is likely an initial/case label."""
    before = original_text[max(0, span.start - 24) : span.start]
    after = original_text[span.end : min(len(original_text), span.end + 24)]
    before_words = before.lower().replace(".", " ").split()
    previous_word = before_words[-1] if before_words else ""

    if previous_word in _INITIAL_CONTEXT_PREFIXES:
        return True
    if after.startswith(".") or after.startswith(" ."):
        return True
    if after.startswith("-"):
        return True
    if len(span.text) == 1 and after[:1].isupper():
        return True
    return False


def _has_nursing_home_context(
    span: PHISpan,
    original_text: str,
) -> bool:
    """Return true for narrow nursing-home shorthand contexts around `NH`."""
    before = original_text[max(0, span.start - 32) : span.start].lower()
    after = original_text[span.end : min(len(original_text), span.end + 32)].lower()
    return any(after.startswith(term) for term in _NH_CONTEXT_AFTER) or any(
        term in before for term in _NH_CONTEXT_BEFORE
    )
