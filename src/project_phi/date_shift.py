"""Stable per-patient date shifting helpers using pyDeid-detected spans.

These helpers never detect dates themselves. They operate only on spans pyDeid
has already found and the project normalization layer has preserved.
"""

from __future__ import annotations

from datetime import date, timedelta
import hashlib
import hmac
import os
import re
from typing import Iterable

from .models import PHISpan

_MONTH_NUMBERS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

_NATURAL_LANGUAGE_FULL_DATE_RE = re.compile(
    r"^\s*([A-Za-z]{3,9})\.?\s+([0-9]{1,2}),\s*([0-9]{4})\s*$",
    re.IGNORECASE,
)
_DAY_MONTH_YEAR_FULL_DATE_RE = re.compile(
    r"^\s*([0-9]{1,2})\s+([A-Za-z]{3,9})\.?,?\s+([0-9]{4})\s*$",
    re.IGNORECASE,
)
_NATURAL_LANGUAGE_MONTH_YEAR_RE = re.compile(
    r"^\s*([A-Za-z]{3,9})\.?\s+([0-9]{4})\s*$",
    re.IGNORECASE,
)
_NATURAL_LANGUAGE_MONTH_DAY_RE = re.compile(
    r"^\s*([A-Za-z]{3,9})\.?\s+([0-9]{1,2})(?:st|nd|rd|th)?\s*$",
    re.IGNORECASE,
)
_NUMERIC_MONTH_DAY_RE = re.compile(r"^\s*([0-9]{1,2})[-/]([0-9]{1,2})\s*$")
_SLASH_SCORE_OR_FRACTION_RE = re.compile(r"^\s*\d{1,2}/\d{1,3}\s*$")
_SLASH_APGAR_SCORE_RE = re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{1,2}\s*$")
_TUMOR_MARKER_NUMBER_RE = re.compile(r"^\s*\d{1,2}(?:[-.]\d{1,2})\s*$")
_APGAR_TIMING_RE = re.compile(
    r"(?:at|@)\s*(?:1|one)\s*(?:,|\band\b|/)\s*(?:5|five)"
    r"(?:\s*(?:,|\band\b|/)\s*(?:10|ten))?\s*(?:min|mins|minute|minutes)\b",
    re.IGNORECASE,
)
_MONTH_YEAR_ANCHOR_DAY = 15
_MONTH_DAY_ANCHOR_YEAR = 2000

_SCORE_OR_FRACTION_CONTEXT_TERMS = {
    "activity score",
    "admission score",
    "apgar",
    "apgar score",
    "apgar scores",
    "assessment",
    "assessment score",
    "assessment tool",
    "barthel",
    "bi-rads",
    "birads",
    "braden",
    "caprini",
    "child-pugh",
    "classification",
    "clinical score",
    "cpax",
    "criteria",
    "disability score",
    "ecog",
    "edss",
    "functional score",
    "functional independence measure",
    "gad-7",
    "gcs",
    "glasgow",
    "glasgow coma scale",
    "gleason",
    "grade",
    "ham-d",
    "hads",
    "index",
    "icu mobility scale",
    "karnofsky",
    "kps",
    "medical research council sum score",
    "moca",
    "modified rankin",
    "mrc",
    "mrc-ss",
    "nihss",
    "performance status",
    "phq-9",
    "physical function icu test",
    "points",
    "score",
    "scored",
    "scoring",
    "scale",
    "short physical performance battery",
    "sppb",
    "tool",
    "updrs",
}

_RATIO_OR_COUNT_CONTEXT_TERMS = {
    "biopsied",
    "biopsy",
    "core",
    "core samples",
    "cores positive",
    "fraction",
    "field",
    "high-power field",
    "hpf",
    "invasion",
    "lymph node",
    "lymph nodes",
    "metastatic lymph node",
    "mitoses",
    "mitotic count",
    "node",
    "nodes",
    "nodes positive",
    "per hpf",
    "positive",
    "positive nodes",
    "ratio",
    "samples",
    "sentinel",
    "sentinel lymph nodes",
    "sentinel nodes",
    "specimens",
    "tumor cells",
}

_STAGING_CONTEXT_TERMS = {
    "cstage",
    "m0",
    "m1",
    "n0",
    "n1",
    "n2",
    "n3",
    "pathologic stage",
    "pathological stage",
    "pt",
    "pt1",
    "pt2",
    "pt3",
    "pt4",
    "stage",
    "staging",
    "ypstage",
    "ypt",
    "ypt1",
    "ypt2",
    "ypt3",
    "ypt4",
}

_VISUAL_ACUITY_CONTEXT_TERMS = {
    "acuity",
    "counting fingers",
    "eye",
    "eyes",
    "fundoscopy",
    "left eye",
    "od",
    "ophthalm",
    "optical",
    "optic",
    "os",
    "ou",
    "right eye",
    "snellen",
    "vision",
    "visual",
    "visual acuity",
}

_TUMOR_MARKER_CONTEXT_TERMS = {
    "afp",
    "ca 125",
    "ca 15-3",
    "ca 19-9",
    "ca 27.29",
    "ca-125",
    "ca15-3",
    "ca19-9",
    "ca27.29",
    "cea",
    "he4",
    "ng/ml",
    "psa",
    "tumor marker",
    "tumour marker",
    "u/ml",
}


def _resolve_date_shift_secret(
    date_shift_secret: str | bytes | None,  # Direct secret value for HMAC.
    date_shift_secret_env_var: str | None,  # Env var name containing the secret.
) -> bytes:
    """Resolve the date-shift secret from direct value or environment variable.

    Secrets are returned as bytes for HMAC use and are never stored in result
    metadata or audit output. Empty direct/env values fail closed with a clear
    setup error.
    """
    if date_shift_secret is not None:
        if isinstance(date_shift_secret, bytes):
            secret = date_shift_secret
        else:
            secret = date_shift_secret.encode("utf-8")
    elif date_shift_secret_env_var:
        env_secret = os.environ.get(date_shift_secret_env_var)
        secret = env_secret.encode("utf-8") if env_secret else b""
    else:
        secret = b""

    if not secret:
        raise ValueError(
            "stable_date_shift=True requires date_shift_secret or a populated "
            "date_shift_secret_env_var."
        )
    return secret


def _stable_date_shift_offset(
    *,
    patient_id: str | None,  # Stable patient key for deterministic offset.
    secret: bytes,  # HMAC key bytes.
    date_shift_days: int,  # Inclusive +/- shift range.
) -> int:
    """Compute the deterministic patient-keyed day offset.

    The inclusive output range is `[-date_shift_days, +date_shift_days]`.
    Only the bounded integer offset is returned; the HMAC digest and secret
    remain internal to this function.
    """
    if not patient_id:
        raise ValueError("stable_date_shift=True requires a nonempty patient_id.")
    if not isinstance(date_shift_days, int) or date_shift_days < 0:
        raise ValueError("date_shift_days must be a nonnegative integer.")

    # The digest only maps patient+secret to an offset; it is never returned or
    # stored in result metadata.
    digest = hmac.new(secret, patient_id.encode("utf-8"), hashlib.sha256).digest()
    bucket = int.from_bytes(digest[:8], "big")
    return (bucket % (2 * date_shift_days + 1)) - date_shift_days


def get_patient_date_shift(
    *,
    patient_id: str | None,
    date_shift_secret: str | bytes | None = None,
    date_shift_secret_env_var: str | None = None,
    date_shift_days: int = 45,
) -> int:
    """Return the patient-specific date-shift offset in whole days.

    This is the public helper for downstream tabular date shifting. It uses the
    same secret resolution, validation, and HMAC offset logic as
    `deidentify_note(..., stable_date_shift=True)`.
    """
    secret = _resolve_date_shift_secret(
        date_shift_secret,
        date_shift_secret_env_var,
    )
    return _stable_date_shift_offset(
        patient_id=patient_id,
        secret=secret,
        date_shift_days=date_shift_days,
    )


def _is_parseable_full_date_span(
    span: PHISpan,  # Normalized pyDeid span to classify.
) -> bool:
    """Return true when normalized pyDeid metadata has day, month, and year."""
    parsed = span.metadata.get("parsed_phi") or {}
    return (
        parsed.get("kind") == "date"
        and parsed.get("day") not in (None, "")
        and parsed.get("month") not in (None, "")
        and parsed.get("year") not in (None, "")
    ) or _parse_natural_language_full_date(span.text) is not None


def _is_parseable_month_year_span(
    span: PHISpan,  # Normalized pyDeid span to classify.
) -> bool:
    """Return true when a pyDeid span can be treated as month/year granularity.

    Parsed pyDeid date metadata is preferred. The natural-language parser is a
    fallback for pyDeid-detected spans whose text is a common `Month YYYY`
    shape.
    """
    parsed = span.metadata.get("parsed_phi") or {}
    return (
        parsed.get("kind") == "date"
        and parsed.get("day") in (None, "")
        and parsed.get("month") not in (None, "")
        and parsed.get("year") not in (None, "")
    ) or _parse_natural_language_month_year(span.text) is not None


def _is_parseable_partial_month_day_span(
    span: PHISpan,  # Normalized pyDeid span to classify.
) -> bool:
    """Return true when a pyDeid span has month/day but no year.

    This supports optional partial month-day shifting. The visible output keeps
    month/day granularity; the implementation uses an internal leap anchor year
    only for calendar arithmetic.
    """
    if span.label != "DATE" or not _is_date_like_span(span):
        return False

    parsed = span.metadata.get("parsed_phi") or {}
    return (
        parsed.get("kind") == "date"
        and parsed.get("day") not in (None, "")
        and parsed.get("month") not in (None, "")
        and parsed.get("year") in (None, "")
        and (
            not str(parsed.get("month")).strip().isdigit()
            or _is_pydeid_month_day_type(span)
        )
    ) or _parse_natural_language_month_day(span.text) is not None or (
        _is_pydeid_month_day_type(span) and _parse_numeric_month_day(span.text) is not None
    )


def _shift_full_date_span(
    span: PHISpan,  # Date span to shift.
    date_shift_offset: int,  # Patient-specific day offset.
) -> str | None:
    """Return shifted full-date text, or `None` if parsed metadata is unsafe."""

    original_date = _date_from_parsed_phi(span)
    if original_date is None:
        original_date = _parse_natural_language_full_date(span.text)
    if original_date is None:
        return None

    shifted_date = original_date + timedelta(days=date_shift_offset)
    if _looks_like_day_month_year_full_date(span.text):
        return f"{shifted_date.day} {_MONTH_NAMES[shifted_date.month]} {shifted_date.year}"
    if _looks_like_natural_language_full_date(span.text):
        return f"{_MONTH_NAMES[shifted_date.month]} {shifted_date.day}, {shifted_date.year}"
    if _looks_like_iso_date(span.text):
        return shifted_date.isoformat()
    return shifted_date.isoformat()


def _date_shift_policy_for_full_date_span(
    span: PHISpan,  # Shifted full-date span.
) -> str:
    """Return the audit policy label for a shifted full-date span."""
    if _looks_like_day_month_year_full_date(span.text):
        return "shifted_day_month_year_natural_language_full_date"
    if _looks_like_natural_language_full_date(span.text):
        return "shifted_natural_language_full_date"
    return "shifted_full_date"


def _shift_month_year_span(
    span: PHISpan,  # Month/year span to shift.
    date_shift_offset: int,  # Patient-specific day offset.
) -> str | None:
    """Return shifted month/year text while preserving month/year granularity."""

    original_date = _month_year_date_from_parsed_phi(span)
    if original_date is None:
        original_date = _parse_natural_language_month_year(span.text)
    if original_date is None:
        return None

    shifted_date = original_date + timedelta(days=date_shift_offset)
    return f"{_MONTH_NAMES[shifted_date.month]} {shifted_date.year}"


def _shift_partial_month_day_span(
    span: PHISpan,  # Partial month/day span to shift.
    date_shift_offset: int,  # Patient-specific day offset.
) -> str | None:
    """Return shifted month/day text while preserving month/day granularity."""

    original_date = _month_day_date_from_parsed_phi(span)
    if original_date is None:
        original_date = _parse_partial_month_day_text(span.text)
    if original_date is None:
        return None

    shifted_date = original_date + timedelta(days=date_shift_offset)
    return f"{_MONTH_NAMES[shifted_date.month]} {shifted_date.day}"


def _date_shift_metadata_for_partial_month_day_span() -> dict[str, int | str]:
    """Return audit metadata describing the partial month/day anchor policy."""
    return {
        "project_date_shift_granularity": "month_day",
        "project_date_shift_anchor_year": _MONTH_DAY_ANCHOR_YEAR,
    }


def _date_shift_metadata_for_month_year_span() -> dict[str, int | str]:
    """Return audit metadata describing the month/year anchor policy."""
    return {
        "project_date_shift_granularity": "month_year",
        "project_date_shift_anchor_day": _MONTH_YEAR_ANCHOR_DAY,
    }


def _is_score_or_fraction_date_span(
    span: PHISpan,  # pyDeid-emitted date-like span to examine.
    original_text: str,  # Full original note for local context only.
) -> bool:
    """Return true for score/ratio fractions misdetected as dates.

    The guard remains pyDeid-first: it only examines spans already emitted as
    date-like by pyDeid. The local context terms are deliberately broad for
    clinical scores, ratios, staging, node counts, and visual-acuity notation,
    but the span itself must be slash-form numeric text.
    """
    if not _is_date_like_span(span):
        return False
    if _is_apgar_slash_score_span(span, original_text):
        return True

    context = _span_context(original_text, span.start, span.end).lower()
    if _TUMOR_MARKER_NUMBER_RE.match(span.text):
        return any(term in context for term in _TUMOR_MARKER_CONTEXT_TERMS)

    if not _SLASH_SCORE_OR_FRACTION_RE.match(span.text):
        return False

    context_terms = (
        _SCORE_OR_FRACTION_CONTEXT_TERMS
        | _RATIO_OR_COUNT_CONTEXT_TERMS
        | _STAGING_CONTEXT_TERMS
        | _VISUAL_ACUITY_CONTEXT_TERMS
        | _TUMOR_MARKER_CONTEXT_TERMS
    )
    return any(term in context for term in context_terms)


def _is_apgar_slash_score_span(
    span: PHISpan,
    original_text: str,
) -> bool:
    """Return true for bounded Apgar score notation such as `4/7/10`.

    Three-part slash text is also a possible date shape, so this guard requires
    both nearby Apgar wording and the usual 1/5/10-minute timing context.
    """
    if not _SLASH_APGAR_SCORE_RE.match(span.text):
        return False
    before = original_text[max(0, span.start - 48) : span.start]
    after = original_text[span.end : min(len(original_text), span.end + 72)]
    return "apgar" in before.casefold() and _APGAR_TIMING_RE.search(after) is not None


def _score_or_fraction_date_metadata() -> dict[str, str]:
    """Return metadata for score/fraction date-veto preservation."""
    return {
        "project_date_shift_policy": "preserved_score_or_fraction",
        "project_date_shift_preservation_reason": "score_or_fraction_context",
    }


def _date_from_parsed_phi(
    span: PHISpan,  # Span with optional pyDeid parsed date metadata.
) -> date | None:
    """Convert pyDeid parsed full-date metadata to `datetime.date` when safe."""
    parsed = span.metadata.get("parsed_phi") or {}
    try:
        month = _month_number(parsed["month"])
        return date(
            _parsed_year_number(parsed["year"]),
            month,
            int(parsed["day"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _month_year_date_from_parsed_phi(
    span: PHISpan,  # Span with optional pyDeid month/year metadata.
) -> date | None:
    """Convert parsed month/year metadata to an internal anchored date."""
    parsed = span.metadata.get("parsed_phi") or {}
    try:
        return date(
            _parsed_year_number(parsed["year"]),
            _month_number(parsed["month"]),
            _MONTH_YEAR_ANCHOR_DAY,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _month_day_date_from_parsed_phi(
    span: PHISpan,  # Span with optional pyDeid partial date metadata.
) -> date | None:
    """Convert parsed month/day metadata to an internal anchored date."""
    parsed = span.metadata.get("parsed_phi") or {}
    try:
        return date(
            _MONTH_DAY_ANCHOR_YEAR,
            _month_number(parsed["month"]),
            int(parsed["day"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _parsed_year_number(
    year_value,
) -> int:
    """Return a full year number from pyDeid parsed date metadata."""
    year_text = str(year_value).strip()
    if not year_text:
        raise ValueError("empty year")
    year = int(year_text)
    if len(year_text) <= 2:
        return 2000 + year if year <= 69 else 1900 + year
    return year


def _parse_natural_language_full_date(
    text: str,  # Span-local text already detected by pyDeid.
) -> date | None:
    # This parser is intentionally span-local: pyDeid has already detected and
    # pruned the candidate date span, so project code is not scanning notes.
    match = _NATURAL_LANGUAGE_FULL_DATE_RE.match(text)
    if match:
        month_text, day_text, year_text = match.groups()
        try:
            return date(int(year_text), _month_number(month_text), int(day_text))
        except (KeyError, ValueError):
            pass

    match = _DAY_MONTH_YEAR_FULL_DATE_RE.match(text)
    if not match:
        return None

    day_text, month_text, year_text = match.groups()
    try:
        return date(int(year_text), _month_number(month_text), int(day_text))
    except (KeyError, ValueError):
        return None


def _parse_natural_language_month_day(
    text: str,  # Span-local text already detected by pyDeid.
) -> date | None:
    # Month/day shifting stays inside pyDeid-emitted date spans and uses a fixed
    # internal leap anchor year so visible output keeps month/day granularity.
    match = _NATURAL_LANGUAGE_MONTH_DAY_RE.match(text)
    if not match:
        return None

    month_text, day_text = match.groups()
    try:
        return date(_MONTH_DAY_ANCHOR_YEAR, _month_number(month_text), int(day_text))
    except (KeyError, ValueError):
        return None


def _parse_numeric_month_day(
    text: str,  # Span-local pyDeid month/day text, possibly placeholder-wrapped.
) -> date | None:
    cleaned = _strip_placeholder_date_wrapper(text)
    match = _NUMERIC_MONTH_DAY_RE.match(cleaned)
    if not match:
        return None

    month_text, day_text = match.groups()
    try:
        return date(_MONTH_DAY_ANCHOR_YEAR, int(month_text), int(day_text))
    except ValueError:
        return None


def _parse_partial_month_day_text(text: str) -> date | None:
    return _parse_natural_language_month_day(text) or _parse_numeric_month_day(text)


def _strip_placeholder_date_wrapper(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("[**") and stripped.endswith("**]"):
        return stripped[3:-3].strip()
    return stripped


def _is_pydeid_month_day_type(span: PHISpan) -> bool:
    types_text = " ".join(span.pydeid_types or []).casefold()
    return "month/day" in types_text or "[mm/dd]" in types_text


def _parse_natural_language_month_year(
    text: str,  # Span-local text already detected by pyDeid.
) -> date | None:
    # Month/year shifting stays inside pyDeid-emitted date spans and uses a
    # fixed internal anchor day so the visible output keeps month/year
    # granularity without inventing a displayed day.
    match = _NATURAL_LANGUAGE_MONTH_YEAR_RE.match(text)
    if not match:
        return None

    month_text, year_text = match.groups()
    try:
        return date(int(year_text), _month_number(month_text), _MONTH_YEAR_ANCHOR_DAY)
    except (KeyError, ValueError):
        return None


def _month_number(
    value: object,  # Numeric or English month value.
) -> int:
    """Normalize numeric or English month values to an integer month number."""
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().rstrip(".")
    if text.isdigit():
        return int(text)
    return _MONTH_NUMBERS[text]


def _looks_like_iso_date(
    text: str,  # Candidate display text.
) -> bool:
    """Return true for the narrow `YYYY-MM-DD` display shape."""
    return (
        len(text) == 10
        and text[4] == "-"
        and text[7] == "-"
        and text[:4].isdigit()
        and text[5:7].isdigit()
        and text[8:].isdigit()
    )


def _looks_like_natural_language_full_date(
    text: str,  # Candidate display text.
) -> bool:
    """Return true for supported English month-name full-date display text."""
    return _NATURAL_LANGUAGE_FULL_DATE_RE.match(text) is not None


def _looks_like_day_month_year_full_date(
    text: str,  # Candidate display text.
) -> bool:
    """Return true for supported day-month-year English date display text."""
    return _DAY_MONTH_YEAR_FULL_DATE_RE.match(text) is not None


def _is_date_like_span(
    span: PHISpan,  # Normalized pyDeid span to classify.
) -> bool:
    """Classify whether a normalized pyDeid span should receive date policy."""
    parsed = span.metadata.get("parsed_phi") or {}
    if parsed.get("kind") == "date" or span.label == "DATE":
        return True
    type_text = _pydeid_type_text(span)
    return any(term in type_text for term in ("date", "month", "day", "year", "holiday", "season"))


def _is_time_span(
    span: PHISpan,  # Normalized pyDeid span to classify.
) -> bool:
    """Return true for pyDeid spans that represent times."""
    parsed = span.metadata.get("parsed_phi") or {}
    return parsed.get("kind") == "time" or span.label == "TIME" or "time" in _pydeid_type_text(span)


def _is_year_only_span(
    span: PHISpan,  # Normalized pyDeid span to classify.
) -> bool:
    """Return true for parsed date spans that contain only a year."""
    parsed = span.metadata.get("parsed_phi") or {}
    return (
        parsed.get("kind") == "date"
        and parsed.get("year") not in (None, "")
        and parsed.get("month") in (None, "")
        and parsed.get("day") in (None, "")
    )


def _is_holiday_or_season_span(
    span: PHISpan,  # Normalized pyDeid span to classify.
) -> bool:
    """Return true for pyDeid types that indicate holiday/season mentions."""
    type_text = _pydeid_type_text(span)
    return "holiday" in type_text or "season" in type_text


def _pydeid_type_text(
    span: PHISpan,  # Span whose pyDeid types should be searched.
) -> str:
    """Join pyDeid type strings into a case-normalized search string."""
    return " ".join(span.pydeid_types or []).lower()


def _span_context(
    text: str,  # Full original note text.
    start: int,  # Span start offset.
    end: int,  # Span end offset.
    *,
    window: int = 90,  # Characters to inspect around the span.
) -> str:
    """Return bounded local context around a pyDeid span."""
    return text[max(0, start - window) : min(len(text), end + window)]


def _requested_types_include_dates(
    requested_types: Iterable[str],  # Caller-requested pyDeid type names.
) -> bool:
    """Return true when caller-requested pyDeid types include date detection."""
    return any(str(requested_type).lower() == "dates" for requested_type in requested_types)
