"""CSV audit row rendering and sanitized warning helpers.

Audit CSVs are internal review artifacts. They include span offsets,
replacement metadata, and policy provenance for review/debugging.

They deliberately omit:
- raw detected PHI text (`PHISpan.text`);
- raw original note text;
- arbitrary exception messages or lower-layer warning text.

Audit CSVs may still contain exact offsets, row identifiers, and synthetic or
project-generated replacements, so they should not be treated as de-identified
training outputs.
"""

from __future__ import annotations

import json
from typing import Any

from .models import PHISpan

# Stable audit CSV column order.
#
# Existing columns should stay in place for compatibility. New fields should be
# appended to the end of this list.
#
# Field meanings:
# - patient_id: Optional patient identifier from the input row or caller metadata.
# - encounter_id: Optional encounter/visit identifier from the input row or caller metadata.
# - note_id: Optional note/document identifier from the input row or caller metadata.
# - span_index: Zero-based index of the detected span within this note.
# - start: Start character offset of the detected span in the original note.
# - end: End character offset of the detected span in the original note.
# - label: Project-normalized PHI category, such as DATE, NAME, CONTACT, ID, or PHI.
# - source: Detection source/provenance, usually pyDeid.
# - action: Final handling decision for the span, such as replaced or preserved.
# - pydeid_types: JSON-encoded list of raw pyDeid type strings for this span.
# - warning: Sanitized warning text. Span rows leave this blank.
# - replacement_source: Layer/policy that supplied the final replacement.
# - project_replacement: ProjectPHI final replacement text, when project reconstruction ran.
# - project_replacement_start: Start offset of the ProjectPHI replacement in the final note.
# - project_replacement_end: End offset of the ProjectPHI replacement in the final note.
# - pydeid_replacement: pyDeid replacement text before ProjectPHI reconstruction.
# - pydeid_surrogate_start: Start offset of the pyDeid surrogate in pyDeid's output text.
# - pydeid_surrogate_end: End offset of the pyDeid surrogate in pyDeid's output text.
# - project_date_shift_days: Number of days applied by ProjectPHI date shifting, if any.
# - project_date_shift_range_days: Configured date-shift range used by the policy.
# - project_date_shift_policy: Date-shift policy name or identifier.
# - project_date_shift_granularity: Visible date granularity preserved by shifting.
# - project_date_shift_anchor_day: Internal anchor day for month/year shifting.
# - project_date_shift_anchor_year: Internal anchor year for month/day shifting.
# - project_name_policy: Patient-name handling policy applied to this span, if any.
# - name_role: Name role/provenance, such as patient, doctor, or alias, when known.
# - alias_match_type: How a configured alias matched the detected span, when applicable.
# - patient_name_style: Optional caller-supplied fake patient given-name style.
# - custom_regex_rule_id: ProjectPHI custom regex rule ID responsible for this span.
# - custom_regex_phi_type: Configured custom regex phi_type associated with this span.
# - project_protected_term_policy: Protected-term handling policy applied to this span.
# - project_protected_term_rule_id: Protected-term rule ID associated with this span.
# - project_protected_term_category: Protected-term category associated with this span.
# - project_protected_component: Risky component preserved inside an approved phrase.
# - project_protected_within_phrase: Normalized approved phrase that allowed preservation.
# - project_title_context_policy: Title-context false-positive policy applied to this span.
# - project_title_context_trigger: Title pattern that made the action-word veto eligible.
# - project_title_context_word: Normalized action word preserved by the veto.
# - project_title_token_policy: Title-token false-positive policy applied to this span.
# - project_title_token: Title token preserved when pyDeid split it into spans.
# - project_title_token_context: Local context that made title preservation eligible.
# - project_ordinary_token_policy: Ordinary-token false-positive policy applied to this span.
# - project_ordinary_token: Short token preserved by the ordinary-token veto.
# - project_ordinary_token_category: Token category, such as pronoun_or_article.
# - project_clinical_abbreviation_policy: Abbreviation false-positive policy applied.
# - project_clinical_abbreviation: Clinical abbreviation preserved by the policy.
# - project_clinical_abbreviation_context: Context family that allowed preservation.
# - project_obstetric_history_policy: Obstetric shorthand preservation policy.
# - project_obstetric_history_pattern: Obstetric shorthand pattern family.
# - project_decimal_code_policy: Dotted numeric contact false-positive policy.
# - project_decimal_code_context: Local/grouping context that allowed preservation.
# - project_clinical_code_policy: Clinical code/phrase false-positive policy.
# - project_clinical_code: Clinical code or phrase preserved by the policy.
# - project_clinical_code_context: Context family that allowed preservation.
# - project_ordinary_clinical_prose_policy: Ordinary clinical prose false-positive policy.
# - project_ordinary_clinical_prose: Ordinary clinical prose token preserved.
# - project_ordinary_clinical_prose_context: Context family that allowed preservation.
#
# Audit rows intentionally omit PHISpan.text and original note text.
AUDIT_COLUMNS = [
    "patient_id",
    "encounter_id",
    "note_id",
    "span_index",
    "start",
    "end",
    "label",
    "source",
    "action",
    "pydeid_types",
    "warning",
    "replacement_source",
    "project_replacement",
    "project_replacement_start",
    "project_replacement_end",
    "pydeid_replacement",
    "pydeid_surrogate_start",
    "pydeid_surrogate_end",
    "project_date_shift_days",
    "project_date_shift_range_days",
    "project_date_shift_policy",
    "project_date_shift_granularity",
    "project_date_shift_anchor_day",
    "project_date_shift_anchor_year",
    "project_name_policy",
    "name_role",
    "alias_match_type",
    "patient_name_style",
    "custom_regex_rule_id",
    "custom_regex_phi_type",
    "project_protected_term_policy",
    "project_protected_term_rule_id",
    "project_protected_term_category",
    "project_protected_component",
    "project_protected_within_phrase",
    "project_title_context_policy",
    "project_title_context_trigger",
    "project_title_context_word",
    "project_title_token_policy",
    "project_title_token",
    "project_title_token_context",
    "project_ordinary_token_policy",
    "project_ordinary_token",
    "project_ordinary_token_category",
    "project_clinical_abbreviation_policy",
    "project_clinical_abbreviation",
    "project_clinical_abbreviation_context",
    "project_obstetric_history_policy",
    "project_obstetric_history_pattern",
    "project_decimal_code_policy",
    "project_decimal_code_context",
    "project_clinical_code_policy",
    "project_clinical_code",
    "project_clinical_code_context",
    "project_ordinary_clinical_prose_policy",
    "project_ordinary_clinical_prose",
    "project_ordinary_clinical_prose_context",
]


def _span_to_audit_row(
    span: PHISpan,
    span_index: int,
) -> dict[str, Any]:
    """Render one normalized span as an audit CSV row.

    The row includes original-note offsets, detection provenance, replacement
    metadata, and policy metadata needed for internal review.

    Raw detected PHI text is deliberately not written. Use `start` and `end` to
    locate the detection in the original note when reviewing in a controlled
    environment.

    Args:
        span: Normalized span to render. `span.text` is not included.
        span_index: Zero-based span position within the note result.

    Returns:
        Dictionary keyed by `AUDIT_COLUMNS`.
    """
    # Audit rows are internal artifacts. They omit raw PHI text, but still
    # include exact offsets and replacement metadata for review/debugging.
    return {
        "patient_id": span.metadata.get("patient_id"),
        "encounter_id": span.metadata.get("encounter_id"),
        "note_id": span.metadata.get("note_id"),
        "span_index": span_index,
        "start": span.start,
        "end": span.end,
        "label": span.label,
        "source": span.source,
        "action": span.action,
        "pydeid_types": json.dumps(span.pydeid_types or []),
        "warning": "",
        "replacement_source": span.metadata.get("replacement_source"),
        "project_replacement": span.metadata.get("project_replacement"),
        "project_replacement_start": span.metadata.get("project_replacement_start"),
        "project_replacement_end": span.metadata.get("project_replacement_end"),
        "pydeid_replacement": span.metadata.get("pydeid_replacement"),
        "pydeid_surrogate_start": span.metadata.get("pydeid_surrogate_start"),
        "pydeid_surrogate_end": span.metadata.get("pydeid_surrogate_end"),
        "project_date_shift_days": span.metadata.get("project_date_shift_days"),
        "project_date_shift_range_days": span.metadata.get("project_date_shift_range_days"),
        "project_date_shift_policy": span.metadata.get("project_date_shift_policy"),
        "project_date_shift_granularity": span.metadata.get("project_date_shift_granularity"),
        "project_date_shift_anchor_day": span.metadata.get("project_date_shift_anchor_day"),
        "project_date_shift_anchor_year": span.metadata.get("project_date_shift_anchor_year"),
        "project_name_policy": span.metadata.get("project_name_policy"),
        "name_role": span.metadata.get("name_role"),
        "alias_match_type": span.metadata.get("alias_match_type"),
        "patient_name_style": span.metadata.get("patient_name_style"),
        "custom_regex_rule_id": span.metadata.get("custom_regex_rule_id"),
        "custom_regex_phi_type": span.metadata.get("custom_regex_phi_type"),
        "project_protected_term_policy": span.metadata.get("project_protected_term_policy"),
        "project_protected_term_rule_id": span.metadata.get("project_protected_term_rule_id"),
        "project_protected_term_category": span.metadata.get("project_protected_term_category"),
        "project_protected_component": span.metadata.get("project_protected_component"),
        "project_protected_within_phrase": span.metadata.get("project_protected_within_phrase"),
        "project_title_context_policy": span.metadata.get("project_title_context_policy"),
        "project_title_context_trigger": span.metadata.get("project_title_context_trigger"),
        "project_title_context_word": span.metadata.get("project_title_context_word"),
        "project_title_token_policy": span.metadata.get("project_title_token_policy"),
        "project_title_token": span.metadata.get("project_title_token"),
        "project_title_token_context": span.metadata.get("project_title_token_context"),
        "project_ordinary_token_policy": span.metadata.get("project_ordinary_token_policy"),
        "project_ordinary_token": span.metadata.get("project_ordinary_token"),
        "project_ordinary_token_category": span.metadata.get("project_ordinary_token_category"),
        "project_clinical_abbreviation_policy": span.metadata.get(
            "project_clinical_abbreviation_policy"
        ),
        "project_clinical_abbreviation": span.metadata.get("project_clinical_abbreviation"),
        "project_clinical_abbreviation_context": span.metadata.get(
            "project_clinical_abbreviation_context"
        ),
        "project_obstetric_history_policy": span.metadata.get("project_obstetric_history_policy"),
        "project_obstetric_history_pattern": span.metadata.get("project_obstetric_history_pattern"),
        "project_decimal_code_policy": span.metadata.get("project_decimal_code_policy"),
        "project_decimal_code_context": span.metadata.get("project_decimal_code_context"),
        "project_clinical_code_policy": span.metadata.get("project_clinical_code_policy"),
        "project_clinical_code": span.metadata.get("project_clinical_code"),
        "project_clinical_code_context": span.metadata.get("project_clinical_code_context"),
        "project_ordinary_clinical_prose_policy": span.metadata.get(
            "project_ordinary_clinical_prose_policy"
        ),
        "project_ordinary_clinical_prose": span.metadata.get("project_ordinary_clinical_prose"),
        "project_ordinary_clinical_prose_context": span.metadata.get(
            "project_ordinary_clinical_prose_context"
        ),
    }


def _write_warning_audit_row(
    audit_writer,
    patient_id: str | None,
    encounter_id: str | None,
    note_id: str | None,
    warning: str,
) -> None:
    """Write a warning-only audit row.

    Warning rows preserve the same audit schema as span rows, but leave
    span-specific fields blank. This makes CSV-level failures or sanitized
    note-level warnings visible without pretending a PHI span was emitted.

    Args:
        audit_writer: CSV `DictWriter` for the audit file.
        patient_id: Optional patient identifier for the source row.
        encounter_id: Optional encounter identifier for the source row.
        note_id: Optional note identifier for the source row.
        warning: Sanitized warning text.
    """
    audit_writer.writerow(
        {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "note_id": note_id,
            "span_index": "",
            "start": "",
            "end": "",
            "label": "",
            "source": "",
            "action": "",
            "pydeid_types": "[]",
            "warning": warning,
            "replacement_source": "",
            "project_replacement": "",
            "project_replacement_start": "",
            "project_replacement_end": "",
            "pydeid_replacement": "",
            "pydeid_surrogate_start": "",
            "pydeid_surrogate_end": "",
            "project_date_shift_days": "",
            "project_date_shift_range_days": "",
            "project_date_shift_policy": "",
            "project_date_shift_granularity": "",
            "project_date_shift_anchor_day": "",
            "project_date_shift_anchor_year": "",
            "project_name_policy": "",
            "name_role": "",
            "alias_match_type": "",
            "custom_regex_rule_id": "",
            "custom_regex_phi_type": "",
            "project_protected_term_policy": "",
            "project_protected_term_rule_id": "",
            "project_protected_term_category": "",
            "project_protected_component": "",
            "project_protected_within_phrase": "",
            "project_title_context_policy": "",
            "project_title_context_trigger": "",
            "project_title_context_word": "",
            "project_title_token_policy": "",
            "project_title_token": "",
            "project_title_token_context": "",
            "project_ordinary_token_policy": "",
            "project_ordinary_token": "",
            "project_ordinary_token_category": "",
            "project_clinical_abbreviation_policy": "",
            "project_clinical_abbreviation": "",
            "project_clinical_abbreviation_context": "",
            "project_obstetric_history_policy": "",
            "project_obstetric_history_pattern": "",
            "project_decimal_code_policy": "",
            "project_decimal_code_context": "",
        }
    )


def _format_row_warning(
    message: str,
    row_number: int,
    patient_id: str | None,
    encounter_id: str | None,
    note_id: str | None,
    exc: Exception | None = None,
    warning_index: int | None = None,
    warning_type: str | None = None,
) -> str:
    """Build a sanitized row warning string.

    The returned string includes structured context only: row number, configured
    IDs, optional exception class, optional warning index, and optional warning
    type. It does not copy arbitrary exception text or lower-layer warning text,
    because those strings could contain raw note text, detected PHI, aliases,
    regex patterns, secrets, hashes, or HMAC digests.

    Args:
        message: Sanitized warning prefix.
        row_number: CSV row number, including the header offset.
        patient_id: Optional patient identifier for the source row.
        encounter_id: Optional encounter identifier for the source row.
        note_id: Optional note identifier for the source row.
        exc: Optional exception. Only the exception class name is included.
        warning_index: Optional index of a note-level warning.
        warning_type: Optional sanitized warning type or class name.

    Returns:
        Sanitized warning string suitable for summaries and audit rows.
    """
    # Include only structured context. Do not copy exception messages because
    # they may contain raw note text, detected PHI, regex patterns, or secrets.
    parts = [
        f"row={row_number}",
        f"patient_id={patient_id!r}",
        f"encounter_id={encounter_id!r}",
        f"note_id={note_id!r}",
    ]
    if exc is not None:
        parts.append(f"error={type(exc).__name__}")
    if warning_index is not None:
        parts.append(f"warning_index={warning_index}")
    if warning_type is not None:
        parts.append(f"warning_type={warning_type}")
    return f"{message}: " + ", ".join(parts)
