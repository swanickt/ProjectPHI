"""Stable per-patient date-shifting helpers for pyDeid-detected spans.

These helpers do not detect dates themselves. They only operate on spans that
pyDeid has already detected and ProjectPHI has normalized into `PHISpan`
objects.

The core policy is:

1. compute one deterministic day offset per patient using HMAC(secret, patient_id);
2. apply that same offset to every parseable date span for that patient;
3. preserve the visible granularity/shape where supported.

Examples:
    With a patient-specific offset of +10 days:

    - `2024-01-05` becomes `2024-01-15`
    - `January 5, 2024` becomes `January 15, 2024`
    - `January 2024` is internally anchored to January 15, shifted by 10 days,
      and displayed as `January 2024`

    With an offset of +25 days:

    - `January 20, 2024` becomes `February 14, 2024`
    - `January 2024` is anchored to January 15, shifted to February 9, and
      displayed as `February 2024`

Coordinate systems:
    - `PHISpan.start` / `PHISpan.end` remain original-note offsets.
    - These helpers return replacement text and metadata only.
    - Final replacement offsets are added later by reconstruction code.
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
_NATURAL_LANGUAGE_MONTH_YEAR_RE = re.compile(
    r"^\s*([A-Za-z]{3,9})\.?\s+([0-9]{4})\s*$",
    re.IGNORECASE,
)
_MONTH_YEAR_ANCHOR_DAY = 15


def _resolve_date_shift_secret(
    date_shift_secret: str | bytes | None,
    date_shift_secret_env_var: str | None,
) -> bytes:
    """Resolve the HMAC secret used for stable date shifting.

    The secret can be supplied directly or through an environment variable.
    Direct values are useful for tests; environment variables are preferred for
    real runtime configuration.

    Examples:
        Direct string secret:
            _resolve_date_shift_secret("dev-secret", None)

        Direct bytes secret:
            _resolve_date_shift_secret(b"dev-secret", None)

        Environment-backed secret:
            os.environ["PROJECTPHI_DATE_SHIFT_SECRET"] = "runtime-secret"
            _resolve_date_shift_secret(None, "PROJECTPHI_DATE_SHIFT_SECRET")

    Args:
        date_shift_secret: Direct secret value. Strings are encoded as UTF-8.
        date_shift_secret_env_var: Name of the environment variable containing
            the secret. Used only when `date_shift_secret` is not provided.

    Returns:
        Secret bytes suitable for HMAC.

    Raises:
        ValueError: If neither source provides a nonempty secret.

    Notes:
        The secret is never stored in span metadata, audit rows, warnings, or
        returned values.
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
    patient_id: str | None,
    secret: bytes,
    date_shift_days: int,
) -> int:
    """Compute one deterministic day offset for a patient.

    The offset is derived from `HMAC-SHA256(secret, patient_id)` and mapped into
    the inclusive range `[-date_shift_days, +date_shift_days]`.

    Examples:
        If `date_shift_days == 30`, the returned offset is between -30 and +30.

        The same `(patient_id, secret, date_shift_days)` always gives the same
        offset, so all notes for a patient shift consistently.

        Different patients usually receive different offsets, which helps avoid
        preserving real calendar dates across patients.

    Args:
        patient_id: Stable patient key used for deterministic shifting.
        secret: HMAC key bytes.
        date_shift_days: Inclusive maximum shift in either direction.

    Returns:
        Integer day offset.

    Raises:
        ValueError: If `patient_id` is empty or `date_shift_days` is not a
            nonnegative integer.

    Notes:
        The HMAC digest is not exposed. Only the final bounded day offset is
        returned.
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


def _is_parseable_full_date_span(
    span: PHISpan,
) -> bool:
    """Return whether a span has enough parsed metadata for full-date shifting.

    A full date needs day, month, and year.

    Examples:
        Parseable full dates:
            - `2024-01-05`
            - `January 5, 2024`
            - parsed metadata: year=2024, month=1, day=5

        Not full dates:
            - `January 2024`
            - `2024`
            - `Spring 2024`
    """
    parsed = span.metadata.get("parsed_phi") or {}
    return (
        parsed.get("kind") == "date"
        and parsed.get("day") not in (None, "")
        and parsed.get("month") not in (None, "")
        and parsed.get("year") not in (None, "")
    )


def _is_parseable_month_year_span(
    span: PHISpan,
) -> bool:
    """Return whether a span can be shifted at month/year granularity.

    Parsed pyDeid metadata is preferred. As a fallback, the span text is checked
    for a common English `Month YYYY` shape.

    Examples:
        Month/year spans:
            - `January 2024`
            - `Jan. 2024`
            - parsed metadata with year and month but no day

        Not month/year spans:
            - `January 5, 2024`
            - `2024-01-05`
            - `2024`
    """
    parsed = span.metadata.get("parsed_phi") or {}
    return (
        parsed.get("kind") == "date"
        and parsed.get("day") in (None, "")
        and parsed.get("month") not in (None, "")
        and parsed.get("year") not in (None, "")
    ) or _parse_natural_language_month_year(span.text) is not None


def _shift_full_date_span(
    span: PHISpan,
    date_shift_offset: int,
) -> str | None:
    """Return shifted full-date text, preserving supported display shapes.

    The original date is read first from pyDeid parsed metadata. If that is not
    available, this function falls back to parsing supported natural-language
    full dates from the span text.

    Examples:
        With offset +10:
            - `2024-01-05` -> `2024-01-15`
            - `January 5, 2024` -> `January 15, 2024`

        With offset -7:
            - `2024-01-05` -> `2023-12-29`
            - `January 5, 2024` -> `December 29, 2023`

    Returns:
        Shifted date text, or `None` when the span cannot be safely parsed.

    Notes:
        ISO-like input is returned as ISO `YYYY-MM-DD`.
        Supported natural-language full dates are returned as `Month D, YYYY`.
        Other parseable full dates currently fall back to ISO output.
    """

    original_date = _date_from_parsed_phi(span)
    if original_date is None:
        original_date = _parse_natural_language_full_date(span.text)
    if original_date is None:
        return None

    shifted_date = original_date + timedelta(days=date_shift_offset)
    if _looks_like_natural_language_full_date(span.text):
        return f"{_MONTH_NAMES[shifted_date.month]} {shifted_date.day}, {shifted_date.year}"
    if _looks_like_iso_date(span.text):
        return shifted_date.isoformat()
    return shifted_date.isoformat()


def _date_shift_policy_for_full_date_span(
    span: PHISpan,
) -> str:
    """Return the audit policy label for a shifted full-date span.

    Examples:
        - `January 5, 2024` -> `shifted_natural_language_full_date`
        - `2024-01-05` -> `shifted_full_date`
    """
    if _looks_like_natural_language_full_date(span.text):
        return "shifted_natural_language_full_date"
    return "shifted_full_date"


def _shift_month_year_span(
    span: PHISpan,
    date_shift_offset: int,
) -> str | None:
    """Return shifted month/year text while preserving month/year granularity.

    Month/year spans do not display a day. Internally, ProjectPHI anchors the
    date to `_MONTH_YEAR_ANCHOR_DAY`, applies the day offset, and then displays
    only `Month YYYY`.

    Examples:
        With anchor day 15 and offset +10:
            - `January 2024` -> internal date `2024-01-15`
            - shifted internal date `2024-01-25`
            - displayed as `January 2024`

        With anchor day 15 and offset +25:
            - `January 2024` -> internal date `2024-01-15`
            - shifted internal date `2024-02-09`
            - displayed as `February 2024`

        With anchor day 15 and offset -20:
            - `January 2024` -> internal date `2024-01-15`
            - shifted internal date `2023-12-26`
            - displayed as `December 2023`

    Returns:
        Shifted `Month YYYY` text, or `None` when the span cannot be safely parsed.
    """

    original_date = _month_year_date_from_parsed_phi(span)
    if original_date is None:
        original_date = _parse_natural_language_month_year(span.text)
    if original_date is None:
        return None

    shifted_date = original_date + timedelta(days=date_shift_offset)
    return f"{_MONTH_NAMES[shifted_date.month]} {shifted_date.year}"


def _date_shift_metadata_for_month_year_span() -> dict[str, int | str]:
    """Return audit metadata for month/year shifting.

    Month/year spans are shifted using a hidden anchor day so that day-level
    offsets can still be applied consistently. The anchor day is recorded in
    metadata because it affects whether the visible month changes.

    Example:
        {
            "project_date_shift_granularity": "month_year",
            "project_date_shift_anchor_day": 15,
        }
    """
    return {
        "project_date_shift_granularity": "month_year",
        "project_date_shift_anchor_day": _MONTH_YEAR_ANCHOR_DAY,
    }


def _date_from_parsed_phi(
    span: PHISpan,
) -> date | None:
    """Convert pyDeid parsed full-date metadata into `datetime.date`.

    Expected parsed metadata shape:
        {
            "kind": "date",
            "year": 2024,
            "month": 1,
            "day": 5,
        }

    Month may be numeric or English text, depending on pyDeid's parsed value.

    Returns:
        A `date` when year, month, and day are valid; otherwise `None`.
    """
    parsed = span.metadata.get("parsed_phi") or {}
    try:
        month = _month_number(parsed["month"])
        return date(
            int(parsed["year"]),
            month,
            int(parsed["day"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _month_year_date_from_parsed_phi(
    span: PHISpan,
) -> date | None:
    """Convert parsed month/year metadata into an anchored internal date.

    Expected parsed metadata shape:
        {
            "kind": "date",
            "year": 2024,
            "month": "January",
            "day": None,
        }

    The returned date uses `_MONTH_YEAR_ANCHOR_DAY` as the day. This lets the
    normal day-offset machinery shift month/year spans while the visible output
    still omits the day.

    Returns:
        Anchored `date` when year and month are valid; otherwise `None`.
    """
    parsed = span.metadata.get("parsed_phi") or {}
    try:
        return date(
            int(parsed["year"]),
            _month_number(parsed["month"]),
            _MONTH_YEAR_ANCHOR_DAY,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _parse_natural_language_full_date(
    text: str,
) -> date | None:
    """Parse supported English full-date span text.

    This parser is intentionally span-local. It only receives text from a
    pyDeid-emitted span; it does not search the full note.

    Supported examples:
        - `January 5, 2024`
        - `Jan 5, 2024`
        - `Jan. 5, 2024`

    Unsupported examples:
        - `2024-01-05`
        - `01/05/2024`
        - `January 2024`
        - `5 January 2024`

    Returns:
        Parsed `date`, or `None`.
    """
    # Span-local fallback parser: pyDeid has already detected and pruned the
    # candidate date span, so ProjectPHI is not scanning the note.
    match = _NATURAL_LANGUAGE_FULL_DATE_RE.match(text)
    if not match:
        return None

    month_text, day_text, year_text = match.groups()
    try:
        return date(int(year_text), _month_number(month_text), int(day_text))
    except (KeyError, ValueError):
        return None


def _parse_natural_language_month_year(
    text: str,
) -> date | None:
    """Parse supported English month/year span text into an anchored date.

    This parser is intentionally span-local. It only receives text from a
    pyDeid-emitted span; it does not search the full note.

    Supported examples:
        - `January 2024`
        - `Jan 2024`
        - `Jan. 2024`

    Unsupported examples:
        - `2024-01`
        - `01/2024`
        - `January 5, 2024`
        - `2024`

    Returns:
        Anchored `date` using `_MONTH_YEAR_ANCHOR_DAY`, or `None`.
    """
    # Use a fixed internal anchor day so month/year spans can shift by days
    # without inventing a visible day in the output.
    match = _NATURAL_LANGUAGE_MONTH_YEAR_RE.match(text)
    if not match:
        return None

    month_text, year_text = match.groups()
    try:
        return date(int(year_text), _month_number(month_text), _MONTH_YEAR_ANCHOR_DAY)
    except (KeyError, ValueError):
        return None


def _month_number(
    value: object,
) -> int:
    """Normalize a numeric or English month value to an integer month.

    Examples:
        - `1` -> `1`
        - `"1"` -> `1`
        - `"Jan"` -> `1`
        - `"Jan."` -> `1`
        - `"January"` -> `1`

    Raises:
        KeyError: If a nonnumeric string is not a known English month name.
        ValueError: If a numeric string cannot be converted to an integer.
    """
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().rstrip(".")
    if text.isdigit():
        return int(text)
    return _MONTH_NUMBERS[text]


def _looks_like_iso_date(
    text: str,  # Candidate display text.
) -> bool:
    """Return whether text has the narrow ISO date display shape `YYYY-MM-DD`.

    Examples:
        - `2024-01-05` -> True
        - `2024-1-5` -> False
        - `01/05/2024` -> False

    This is a shape check, not full calendar validation.
    """
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
    """Return whether text matches a supported English full-date display shape.

    Examples:
        - `January 5, 2024` -> True
        - `Jan. 5, 2024` -> True
        - `January 2024` -> False
        - `2024-01-05` -> False
    """
    return _NATURAL_LANGUAGE_FULL_DATE_RE.match(text) is not None


def _is_date_like_span(
    span: PHISpan,
) -> bool:
    """Return whether a normalized pyDeid span should receive date policy.

    A span is date-like when:
    - parsed metadata says it is a date;
    - ProjectPHI normalized its label to `DATE`; or
    - raw pyDeid type strings mention date-related categories.

    Examples of date-like spans:
        - full dates, such as `2024-01-05`
        - month/year mentions, such as `January 2024`
        - year-only spans
        - holidays or seasons, when pyDeid labels them as date-related

    Notes:
        This function classifies date-like spans broadly. More specific helpers
        decide whether a span is a parseable full date, month/year span,
        year-only span, holiday/season span, or time span.
    """
    parsed = span.metadata.get("parsed_phi") or {}
    if parsed.get("kind") == "date" or span.label == "DATE":
        return True
    type_text = _pydeid_type_text(span)
    return any(term in type_text for term in ("date", "month", "day", "year", "holiday", "season"))


def _is_time_span(
    span: PHISpan,
) -> bool:
    """Return whether a normalized pyDeid span represents a time.

    Examples:
        - `14:30`
        - `2:30 PM`
        - parsed metadata with `kind == "time"`

    Time spans are separated from date spans because day shifting should not
    change clock times.
    """
    parsed = span.metadata.get("parsed_phi") or {}
    return parsed.get("kind") == "time" or span.label == "TIME" or "time" in _pydeid_type_text(span)


def _is_year_only_span(
    span: PHISpan,
) -> bool:
    """Return whether parsed pyDeid metadata contains only a year.

    Examples:
        Year-only:
            - parsed metadata: year=2024, month=None, day=None

        Not year-only:
            - `January 2024`
            - `January 5, 2024`
            - `2024-01-05`

    Year-only spans should generally not receive a day-level shift because doing
    so would require inventing an unseen month/day.
    """
    parsed = span.metadata.get("parsed_phi") or {}
    return (
        parsed.get("kind") == "date"
        and parsed.get("year") not in (None, "")
        and parsed.get("month") in (None, "")
        and parsed.get("day") in (None, "")
    )


def _is_holiday_or_season_span(
    span: PHISpan,
) -> bool:
    """Return whether pyDeid types indicate a holiday or season mention.

    Examples:
        - `Christmas`
        - `Thanksgiving`
        - `Spring`
        - `Summer 2024`

    Holiday/season spans are date-like, but may not be safely shiftable as
    calendar dates without additional policy.
    """
    type_text = _pydeid_type_text(span)
    return "holiday" in type_text or "season" in type_text


def _pydeid_type_text(
    span: PHISpan,
) -> str:
    """Join raw pyDeid type strings into a lowercase search string.

    Example:
        `["Month", "Year"]` becomes `"month year"`.

    This is used only for coarse policy classification.
    """
    return " ".join(span.pydeid_types or []).lower()


def _requested_types_include_dates(
    requested_types: Iterable[str],
) -> bool:
    """Return whether caller-requested pyDeid types include date detection.

    Examples:
        - `["names", "dates"]` -> True
        - `["names", "contact"]` -> False
        - `["Dates"]` -> True

    This checks for pyDeid's plural `"dates"` category name.
    """
    return any(str(requested_type).lower() == "dates" for requested_type in requested_types)
