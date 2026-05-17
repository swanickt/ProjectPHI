"""Normalize pyDeid surrogate records into ProjectPHI span records.

pyDeid returns table-like surrogate dictionaries from `deid_string(...)`.
Each dictionary represents one detected/pruned PHI span, not one CSV input row.

This module converts those raw pyDeid records into ProjectPHI's stable
`PHISpan` model while preserving pyDeid metadata. It does not decide which spans
exist, prune overlapping spans, or run replacement policies.

Offset convention:
- `PHISpan.start` and `PHISpan.end` are offsets in the original note.
- `pydeid_surrogate_start` and `pydeid_surrogate_end` are offsets in pyDeid's
  initially de-identified output text.
- ProjectPHI final replacement offsets, when added later, should use separate
  `project_replacement_start` / `project_replacement_end` metadata fields.
"""

from __future__ import annotations

from typing import Any, Iterable

from .models import PHISpan


def normalize_surrogates(
    surrogates: Iterable[dict[str, Any]],
    *,
    patient_id: str | None = None,
    encounter_id: str | None = None,
    note_id: str | None = None,
    custom_regex_metadata: dict[str, dict[str, str]] | None = None,
) -> tuple[list[PHISpan], list[str]]:
    """Convert raw pyDeid surrogate records into normalized `PHISpan` objects.

    Args:
        surrogates: Raw dictionaries returned by pyDeid `deid_string(...)`.
            Each record should include original-note offsets, original PHI text,
            replacement text, and pyDeid type metadata.
        patient_id: Optional patient identifier copied into each span's metadata
            for audit/CSV context.
        encounter_id: Optional encounter identifier copied into each span's
            metadata for audit/CSV context.
        note_id: Optional note identifier copied into each span's metadata for
            audit/CSV context.
        custom_regex_metadata: Safe ProjectPHI custom-regex provenance keyed by
            configured pyDeid `phi_type`. When a pyDeid span reports a matching
            type, that provenance is copied into the span metadata.

    Returns:
        A pair `(spans, warnings)`, where `spans` contains normalized PHI spans
        and `warnings` contains sanitized messages for malformed pyDeid records
        that were skipped.

    Notes:
        `PHISpan.start` and `PHISpan.end` always refer to the original note.
        pyDeid replacement offsets are retained only in metadata under
        `pydeid_surrogate_start` and `pydeid_surrogate_end`.
    """
    spans: list[PHISpan] = []
    warnings: list[str] = []

    for index, surrogate in enumerate(surrogates):
        try:
            start = int(surrogate["phi_start"])
            end = int(surrogate["phi_end"])
            phi_value = surrogate["phi"]
        except (KeyError, TypeError, ValueError) as exc:
            warnings.append(
                f"Skipping malformed pyDeid surrogate at index {index} "
                f"for note_id={note_id!r}, encounter_id={encounter_id!r}: {exc}"
            )
            continue

        text, parsed_metadata = _normalize_phi_value(phi_value)
        pydeid_types = list(surrogate.get("types") or [])
        span_metadata = {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "note_id": note_id,
            "pydeid_replacement": surrogate.get("surrogate"),
            "pydeid_surrogate_start": surrogate.get("surrogate_start"),
            "pydeid_surrogate_end": surrogate.get("surrogate_end"),
        }
        if parsed_metadata:
            span_metadata["parsed_phi"] = parsed_metadata
        for pydeid_type in pydeid_types:
            custom_metadata = (custom_regex_metadata or {}).get(pydeid_type)
            if custom_metadata is not None:
                span_metadata.update(custom_metadata)
                break

        spans.append(
            PHISpan(
                start=start,
                end=end,
                text=text,
                label=_label_from_pydeid_types(pydeid_types),
                source="pyDeid",
                confidence=None,
                rule_id=None,
                section=None,
                action="replaced",
                replacement=surrogate.get("surrogate"),
                pydeid_types=pydeid_types,
                metadata=span_metadata,
            )
        )

    return spans, warnings


def _normalize_phi_value(
    phi_value: Any,
) -> tuple[str, dict[str, Any]]:
    """Normalize pyDeid's raw `phi` value into text plus parsed metadata.

    pyDeid usually stores PHI values as strings, but parsed dates and times may
    arrive as namedtuple-like objects. This helper returns:

    - display text, used as the original detected span text; and
    - parsed date/time components, used later by ProjectPHI replacement policies.

    Args:
        phi_value: Raw pyDeid `phi` value.

    Returns:
        A pair `(text, parsed_metadata)`. `parsed_metadata` is empty for ordinary
        string-like PHI values.
    """
    # pyDeid represents parsed dates/times as namedtuple-like objects. Keep the
    # readable text for original-offset checks and preserve parsed components for
    # project-level replacement policies.
    if hasattr(phi_value, "date_string"):
        return (
            str(phi_value.date_string),
            {
                "kind": "date",
                "day": getattr(phi_value, "day", None),
                "month": getattr(phi_value, "month", None),
                "year": getattr(phi_value, "year", None),
            },
        )
    if hasattr(phi_value, "time_string"):
        return (
            str(phi_value.time_string),
            {
                "kind": "time",
                "hours": getattr(phi_value, "hours", None),
                "minutes": getattr(phi_value, "minutes", None),
                "seconds": getattr(phi_value, "seconds", None),
                "meridiem": getattr(phi_value, "meridiem", None),
            },
        )

    return str(phi_value), {}


def _label_from_pydeid_types(
    pydeid_types: Iterable[str],
) -> str:
    """Map pyDeid type strings to one broad ProjectPHI label.

    Raw pyDeid types are still stored on `PHISpan.pydeid_types`. The returned
    label is only a coarse category used by audits, tests, and policy branching.

    Args:
        pydeid_types: Raw type strings reported by pyDeid.

    Returns:
        A broad ProjectPHI label such as `TIME`, `DATE`, `ID`, `CONTACT`,
        `HOSPITAL`, `LOCATION`, `NAME`, or fallback `PHI`.
    """
    joined = " ".join(pydeid_types).lower()
    checks = [
        ("TIME", ("time",)),
        ("DATE", ("date", "month", "day", "year", "holiday")),
        ("ID", ("mrn", "sin", "ohip", "_id (mll)")),
        ("CONTACT", ("telephone/fax", "email address")),
        ("HOSPITAL", ("hospital", "site acronym")),
        ("LOCATION", ("address", "location", "postalcode", "postal_code")),
        ("NAME", ("name", "initials", "first_name (mll)", "last_name (mll)")),
    ]
    for label, needles in checks:
        if any(needle in joined for needle in needles):
            return label
    return "PHI"
