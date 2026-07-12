"""CSV adapter around the single-note de-identification wrapper.

This module deliberately does not call pyDeid's CSV workflow. Keeping CSV
processing as a thin row loop preserves project span metadata and audit policy.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .audit import (
    AUDIT_COLUMNS,
    _format_row_warning,
    _span_to_audit_row,
    _write_warning_audit_row,
)
from .note import deidentify_note
from .patient_batch import deidentify_patient_notes


def deidentify_csv(
    input_file,  # Input CSV path or path-like object.
    output_file,  # De-identified output CSV path or path-like object.
    *,
    audit_output_file=None,  # Optional internal audit CSV path.
    note_text_column="note_text",  # Column containing note text to replace.
    patient_id_column="patient_id",  # Optional patient ID column name.
    encounter_id_column="encounter_id",  # Optional encounter ID column name.
    note_id_column="note_id",  # Optional note ID column name.
    types=None,  # pyDeid PHI categories to request per row.
    custom_dr_first_names=None,  # Extra doctor first names for pyDeid.
    custom_dr_last_names=None,  # Extra doctor last names for pyDeid.
    custom_patient_first_names=None,  # Extra patient first names for pyDeid.
    custom_patient_last_names=None,  # Extra patient last names for pyDeid.
    encoding="utf-8",  # CSV file encoding.
    stable_date_shift: bool = False,  # Enable project HMAC date replacement.
    date_shift_secret: str | bytes | None = None,  # Direct date-shift secret.
    date_shift_secret_env_var: str | None = None,  # Env var containing date secret.
    date_shift_days: int = 45,  # Inclusive +/- date shift range.
    shift_partial_month_day_dates: bool = True,  # Month Day date shifting.
    stable_patient_name_surrogates: bool = False,  # Enable explicit-alias patient names.
    patient_aliases_by_patient_id: dict[str, Iterable[str]] | None = None,  # Row alias lookup.
    patient_name_styles_by_patient_id: dict[str, str] | None = None,  # Optional style lookup.
    patient_name_secret: str | bytes | None = None,  # Direct patient-name secret.
    patient_name_secret_env_var: str | None = None,  # Env var containing name secret.
    stable_provider_name_surrogates: bool = False,  # Enable explicit-provider aliases.
    provider_aliases_by_provider_id: dict[str, Iterable[str]] | None = None,  # Provider aliases.
    provider_name_secret: str | bytes | None = None,  # Direct provider-name secret.
    provider_name_secret_env_var: str | None = None,  # Env var containing provider secret.
    stable_unknown_name_surrogates: bool = False,  # Enable grouped patient-local names.
    unknown_name_secret: str | bytes | None = None,  # Direct unknown-name secret.
    unknown_name_secret_env_var: str | None = None,  # Env var containing unknown-name secret.
    custom_regexes=None,  # Project custom regex config passed to pyDeid.
    protected_clinical_terms=None,  # Runtime protected-term false-positive vetoes.
    include_builtin_protected_clinical_terms: bool = True,  # Include built-in term set.
):
    """De-identify a CSV by applying the ProjectPHI note workflow.

    Parameters are intentionally close to the single-note API. File path values
    may be strings or path-like objects. The configured note text column is the
    only data column replaced for successful rows; all other input columns and
    row order are preserved.

    By default, rows are processed independently with `deidentify_note(...)`.
    When `stable_unknown_name_surrogates=True`, rows are grouped by
    `patient_id_column` and processed with `deidentify_patient_notes(...)` so
    remaining pyDeid-detected unknown names are stable within each patient.

    Failure behavior:
    - the input, output, and optional audit paths must be distinct;
    - the note text column is validated before row processing;
    - failed rows are omitted from de-identified output;
    - row failures increment `rows_failed` and produce sanitized warning text;
    - arbitrary exception messages are not copied into summary/audit output.

    Audit behavior:
    - when `audit_output_file` is provided, one audit row is written per span;
    - warning-only audit rows are written for row failures/warnings;
    - audit rows omit raw note text and raw detected `span.text` by default.

    Returns a summary dictionary with `rows_read`, `rows_written`,
    `rows_failed`, `spans_written`, and `warnings`.
    """
    input_path = Path(input_file)
    output_path = Path(output_file)
    resolved_input_path = input_path.resolve()
    resolved_output_path = output_path.resolve()
    if resolved_input_path == resolved_output_path:
        raise ValueError("input_file and output_file must not be the same path.")
    if audit_output_file is not None:
        resolved_audit_path = Path(audit_output_file).resolve()
        if resolved_audit_path == resolved_input_path:
            raise ValueError("audit_output_file and input_file must not be the same path.")
        if resolved_audit_path == resolved_output_path:
            raise ValueError("audit_output_file and output_file must not be the same path.")

    summary = {
        "rows_read": 0,
        "rows_written": 0,
        "rows_failed": 0,
        "spans_written": 0,
        "warnings": [],
    }

    audit_handle = None
    audit_writer = None

    try:
        if audit_output_file is not None:
            audit_handle = open(audit_output_file, "w", newline="", encoding=encoding)
            audit_writer = csv.DictWriter(audit_handle, fieldnames=AUDIT_COLUMNS)
            audit_writer.writeheader()

        with open(input_path, newline="", encoding=encoding) as input_handle:
            reader = csv.DictReader(input_handle)
            fieldnames = reader.fieldnames or []
            if note_text_column not in fieldnames:
                raise ValueError(
                    f"Required note text column {note_text_column!r} not found in input CSV."
                )
            if stable_unknown_name_surrogates and patient_id_column not in fieldnames:
                raise ValueError(
                    "stable_unknown_name_surrogates=True requires patient_id_column "
                    "to exist in input CSV."
                )

            with open(output_path, "w", newline="", encoding=encoding) as output_handle:
                writer = csv.DictWriter(output_handle, fieldnames=fieldnames)
                writer.writeheader()

                if stable_unknown_name_surrogates:
                    _deidentify_csv_grouped_by_patient(
                        reader,
                        writer=writer,
                        audit_writer=audit_writer,
                        summary=summary,
                        fieldnames=fieldnames,
                        note_text_column=note_text_column,
                        patient_id_column=patient_id_column,
                        encounter_id_column=encounter_id_column,
                        note_id_column=note_id_column,
                        types=types,
                        custom_dr_first_names=custom_dr_first_names,
                        custom_dr_last_names=custom_dr_last_names,
                        custom_patient_first_names=custom_patient_first_names,
                        custom_patient_last_names=custom_patient_last_names,
                        stable_date_shift=stable_date_shift,
                        date_shift_secret=date_shift_secret,
                        date_shift_secret_env_var=date_shift_secret_env_var,
                        date_shift_days=date_shift_days,
                        shift_partial_month_day_dates=shift_partial_month_day_dates,
                        stable_patient_name_surrogates=stable_patient_name_surrogates,
                        patient_aliases_by_patient_id=patient_aliases_by_patient_id,
                        patient_name_styles_by_patient_id=patient_name_styles_by_patient_id,
                        patient_name_secret=patient_name_secret,
                        patient_name_secret_env_var=patient_name_secret_env_var,
                        stable_provider_name_surrogates=stable_provider_name_surrogates,
                        provider_aliases_by_provider_id=provider_aliases_by_provider_id,
                        provider_name_secret=provider_name_secret,
                        provider_name_secret_env_var=provider_name_secret_env_var,
                        unknown_name_secret=unknown_name_secret,
                        unknown_name_secret_env_var=unknown_name_secret_env_var,
                        custom_regexes=custom_regexes,
                        protected_clinical_terms=protected_clinical_terms,
                        include_builtin_protected_clinical_terms=(
                            include_builtin_protected_clinical_terms
                        ),
                    )
                    reader = []

                for row_number, row in enumerate(reader, start=2):
                    summary["rows_read"] += 1
                    patient_id = _optional_row_value(row, fieldnames, patient_id_column)
                    encounter_id = _optional_row_value(row, fieldnames, encounter_id_column)
                    note_id = _optional_row_value(row, fieldnames, note_id_column)

                    try:
                        patient_aliases = _patient_aliases_for_row(
                            patient_id,
                            patient_aliases_by_patient_id,
                            stable_patient_name_surrogates=stable_patient_name_surrogates,
                        )
                        patient_name_style = _patient_name_style_for_row(
                            patient_id,
                            patient_name_styles_by_patient_id,
                        )
                        result = deidentify_note(
                            row.get(note_text_column) or "",
                            patient_id=patient_id,
                            encounter_id=encounter_id,
                            note_id=note_id,
                            include_original_text=False,
                            types=types,
                            custom_dr_first_names=custom_dr_first_names,
                            custom_dr_last_names=custom_dr_last_names,
                            custom_patient_first_names=custom_patient_first_names,
                            custom_patient_last_names=custom_patient_last_names,
                            named_entity_recognition=False,
                            stable_date_shift=stable_date_shift,
                            date_shift_secret=date_shift_secret,
                            date_shift_secret_env_var=date_shift_secret_env_var,
                            date_shift_days=date_shift_days,
                            shift_partial_month_day_dates=shift_partial_month_day_dates,
                            stable_patient_name_surrogates=stable_patient_name_surrogates,
                            patient_aliases=patient_aliases,
                            patient_name_style=patient_name_style,
                            patient_name_secret=patient_name_secret,
                            patient_name_secret_env_var=patient_name_secret_env_var,
                            stable_provider_name_surrogates=stable_provider_name_surrogates,
                            provider_aliases_by_provider_id=provider_aliases_by_provider_id,
                            provider_name_secret=provider_name_secret,
                            provider_name_secret_env_var=provider_name_secret_env_var,
                            custom_regexes=custom_regexes,
                            protected_clinical_terms=protected_clinical_terms,
                            include_builtin_protected_clinical_terms=(
                                include_builtin_protected_clinical_terms
                            ),
                        )
                    except Exception as exc:
                        # Omit failed rows and emit sanitized context only. Raw
                        # notes or arbitrary exception text must not enter audit.
                        summary["rows_failed"] += 1
                        warning = _format_row_warning(
                            "Row failed",
                            row_number,
                            patient_id,
                            encounter_id,
                            note_id,
                            exc,
                        )
                        summary["warnings"].append(warning)
                        if audit_writer is not None:
                            _write_warning_audit_row(
                                audit_writer,
                                patient_id,
                                encounter_id,
                                note_id,
                                warning,
                            )
                        continue

                    output_row = dict(row)
                    output_row[note_text_column] = result.deidentified_text
                    writer.writerow(output_row)
                    summary["rows_written"] += 1

                    if audit_writer is not None:
                        for span_index, span in enumerate(result.spans):
                            audit_writer.writerow(_span_to_audit_row(span, span_index))
                            summary["spans_written"] += 1

                    for warning_index, warning_text in enumerate(result.warnings):
                        warning = _format_row_warning(
                            "Row warning",
                            row_number,
                            patient_id,
                            encounter_id,
                            note_id,
                            warning_index=warning_index,
                            warning_type=type(warning_text).__name__,
                        )
                        summary["warnings"].append(warning)
                        if audit_writer is not None:
                            _write_warning_audit_row(
                                audit_writer,
                                patient_id,
                                encounter_id,
                                note_id,
                                warning,
                            )

    finally:
        if audit_handle is not None:
            audit_handle.close()

    return summary


def _deidentify_csv_grouped_by_patient(
    reader,
    *,
    writer,
    audit_writer,
    summary: dict[str, Any],
    fieldnames: list[str],
    note_text_column: str,
    patient_id_column: str,
    encounter_id_column: str,
    note_id_column: str,
    types,
    custom_dr_first_names,
    custom_dr_last_names,
    custom_patient_first_names,
    custom_patient_last_names,
    stable_date_shift: bool,
    date_shift_secret: str | bytes | None,
    date_shift_secret_env_var: str | None,
    date_shift_days: int,
    shift_partial_month_day_dates: bool,
    stable_patient_name_surrogates: bool,
    patient_aliases_by_patient_id: dict[str, Iterable[str]] | None,
    patient_name_styles_by_patient_id: dict[str, str] | None,
    patient_name_secret: str | bytes | None,
    patient_name_secret_env_var: str | None,
    stable_provider_name_surrogates: bool,
    provider_aliases_by_provider_id: dict[str, Iterable[str]] | None,
    provider_name_secret: str | bytes | None,
    provider_name_secret_env_var: str | None,
    unknown_name_secret: str | bytes | None,
    unknown_name_secret_env_var: str | None,
    custom_regexes,
    protected_clinical_terms,
    include_builtin_protected_clinical_terms: bool,
) -> None:
    """Process a CSV in patient groups while preserving original row order."""
    input_rows = [(row_number, row) for row_number, row in enumerate(reader, start=2)]
    summary["rows_read"] += len(input_rows)
    groups: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    failed_row_numbers: set[int] = set()

    for row_number, row in input_rows:
        patient_id = _optional_row_value(row, fieldnames, patient_id_column)
        encounter_id = _optional_row_value(row, fieldnames, encounter_id_column)
        note_id = _optional_row_value(row, fieldnames, note_id_column)
        if not patient_id:
            _record_row_failure(
                summary,
                audit_writer,
                row_number,
                patient_id,
                encounter_id,
                note_id,
                ValueError("stable_unknown_name_surrogates=True requires a nonempty patient_id."),
            )
            failed_row_numbers.add(row_number)
            continue
        groups[patient_id].append((row_number, row))

    results_by_row_number = {}
    for patient_id, group_rows in groups.items():
        try:
            patient_aliases = _patient_aliases_for_row(
                patient_id,
                patient_aliases_by_patient_id,
                stable_patient_name_surrogates=stable_patient_name_surrogates,
            )
            patient_name_style = _patient_name_style_for_row(
                patient_id,
                patient_name_styles_by_patient_id,
            )
            batch = deidentify_patient_notes(
                [
                    {
                        "patient_id": patient_id,
                        "encounter_id": _optional_row_value(
                            row,
                            fieldnames,
                            encounter_id_column,
                        ),
                        "note_id": _optional_row_value(row, fieldnames, note_id_column),
                        "note_text": row.get(note_text_column) or "",
                    }
                    for _row_number, row in group_rows
                ],
                patient_id=patient_id,
                include_original_text=False,
                types=types,
                custom_dr_first_names=custom_dr_first_names,
                custom_dr_last_names=custom_dr_last_names,
                custom_patient_first_names=custom_patient_first_names,
                custom_patient_last_names=custom_patient_last_names,
                named_entity_recognition=False,
                stable_date_shift=stable_date_shift,
                date_shift_secret=date_shift_secret,
                date_shift_secret_env_var=date_shift_secret_env_var,
                date_shift_days=date_shift_days,
                shift_partial_month_day_dates=shift_partial_month_day_dates,
                stable_patient_name_surrogates=stable_patient_name_surrogates,
                patient_aliases=patient_aliases,
                patient_name_style=patient_name_style,
                patient_name_secret=patient_name_secret,
                patient_name_secret_env_var=patient_name_secret_env_var,
                stable_provider_name_surrogates=stable_provider_name_surrogates,
                provider_aliases_by_provider_id=provider_aliases_by_provider_id,
                provider_name_secret=provider_name_secret,
                provider_name_secret_env_var=provider_name_secret_env_var,
                stable_unknown_name_surrogates=True,
                unknown_name_secret=unknown_name_secret,
                unknown_name_secret_env_var=unknown_name_secret_env_var,
                custom_regexes=custom_regexes,
                protected_clinical_terms=protected_clinical_terms,
                include_builtin_protected_clinical_terms=(
                    include_builtin_protected_clinical_terms
                ),
            )
        except Exception as exc:
            for row_number, row in group_rows:
                _record_row_failure(
                    summary,
                    audit_writer,
                    row_number,
                    patient_id,
                    _optional_row_value(row, fieldnames, encounter_id_column),
                    _optional_row_value(row, fieldnames, note_id_column),
                    exc,
                )
                failed_row_numbers.add(row_number)
            continue

        for (row_number, _row), result in zip(group_rows, batch.results):
            results_by_row_number[row_number] = result

    for row_number, row in input_rows:
        if row_number in failed_row_numbers:
            continue
        result = results_by_row_number.get(row_number)
        if result is None:
            continue
        _write_successful_row(
            writer,
            audit_writer,
            summary,
            row,
            result,
            note_text_column=note_text_column,
            row_number=row_number,
            patient_id=_optional_row_value(row, fieldnames, patient_id_column),
            encounter_id=_optional_row_value(row, fieldnames, encounter_id_column),
            note_id=_optional_row_value(row, fieldnames, note_id_column),
        )


def _write_successful_row(
    writer,
    audit_writer,
    summary: dict[str, Any],
    row: dict[str, Any],
    result,
    *,
    note_text_column: str,
    row_number: int,
    patient_id: str | None,
    encounter_id: str | None,
    note_id: str | None,
) -> None:
    """Write one successful output row and optional audit rows."""
    output_row = dict(row)
    output_row[note_text_column] = result.deidentified_text
    writer.writerow(output_row)
    summary["rows_written"] += 1

    if audit_writer is not None:
        for span_index, span in enumerate(result.spans):
            audit_writer.writerow(_span_to_audit_row(span, span_index))
            summary["spans_written"] += 1

    for warning_index, warning_text in enumerate(result.warnings):
        warning = _format_row_warning(
            "Row warning",
            row_number,
            patient_id,
            encounter_id,
            note_id,
            warning_index=warning_index,
            warning_type=type(warning_text).__name__,
        )
        summary["warnings"].append(warning)
        if audit_writer is not None:
            _write_warning_audit_row(
                audit_writer,
                patient_id,
                encounter_id,
                note_id,
                warning,
            )


def _record_row_failure(
    summary: dict[str, Any],
    audit_writer,
    row_number: int,
    patient_id: str | None,
    encounter_id: str | None,
    note_id: str | None,
    exc: Exception,
) -> None:
    """Record one sanitized CSV row failure."""
    summary["rows_failed"] += 1
    warning = _format_row_warning(
        "Row failed",
        row_number,
        patient_id,
        encounter_id,
        note_id,
        exc,
    )
    summary["warnings"].append(warning)
    if audit_writer is not None:
        _write_warning_audit_row(
            audit_writer,
            patient_id,
            encounter_id,
            note_id,
            warning,
        )


def _optional_row_value(
    row: dict[str, Any],  # Current CSV row.
    fieldnames: list[str],  # Input CSV header names.
    column: str,  # Optional column to read.
) -> str | None:
    """Return a configured optional ID column value only when the column exists."""
    if column in fieldnames:
        return row.get(column)
    return None


def _patient_aliases_for_row(
    patient_id: str | None,  # Row patient ID used as alias key.
    patient_aliases_by_patient_id: dict[str, Iterable[str]] | None,  # Alias manifest mapping.
    *,
    stable_patient_name_surrogates: bool,  # Whether aliases are required.
) -> Iterable[str] | None:
    """Select row-specific aliases for stable patient-name replacement.

    Stable patient-name surrogates require explicit aliases keyed by the row's
    `patient_id`. Missing IDs or aliases fail through the normal row-failure
    path so the affected row is omitted rather than processed with guessed
    patient-name identity.
    """
    if not stable_patient_name_surrogates:
        return None
    if not patient_id:
        raise ValueError("stable_patient_name_surrogates=True requires a nonempty patient_id.")
    if patient_aliases_by_patient_id is None:
        raise ValueError(
            "stable_patient_name_surrogates=True requires patient_aliases_by_patient_id."
        )
    aliases = patient_aliases_by_patient_id.get(patient_id)
    if not aliases:
        raise ValueError("stable_patient_name_surrogates=True requires aliases for patient_id.")
    return aliases


def _patient_name_style_for_row(
    patient_id: str | None,
    patient_name_styles_by_patient_id: dict[str, str] | None,
) -> str | None:
    """Return optional explicit fake-name style for this patient."""
    if not patient_id or patient_name_styles_by_patient_id is None:
        return None
    return patient_name_styles_by_patient_id.get(patient_id)
