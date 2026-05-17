"""CSV adapter around the single-note ProjectPHI workflow.

This module deliberately does not call pyDeid's CSV workflow. Instead, it reads
the input CSV row by row and applies `deidentify_note(...)` to one configured
note-text column.

This keeps CSV processing thin and lets ProjectPHI preserve:
- normalized `PHISpan` metadata;
- project replacement metadata;
- sanitized warning behavior;
- optional audit CSV output.

Behavior summary:
- input, output, and audit paths must be distinct;
- the configured note-text column is required;
- only the note-text column is replaced in successful output rows;
- all other input columns and row order are preserved for successful rows;
- failed rows are omitted from the de-identified output;
- failures and note-level warnings are reported with sanitized context only.

Example:
    summary = deidentify_csv(
        "input.csv",
        "deidentified.csv",
        audit_output_file="audit.csv",
        note_text_column="note_text",
        patient_id_column="patient_id",
        stable_date_shift=True,
        date_shift_secret_env_var="PROJECTPHI_DATE_SHIFT_SECRET",
    )

Stable patient-name example:
    summary = deidentify_csv(
        "input.csv",
        "deidentified.csv",
        patient_id_column="patient_id",
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={
            "P001": ["Jane Smith", "Jane", "Ms Smith"],
            "P002": ["Robert Chen", "Mr Chen"],
        },
        patient_name_secret_env_var="PROJECTPHI_PATIENT_NAME_SECRET",
    )

Audit notes:
- audit rows include offsets, replacements, and policy metadata;
- audit rows do not include raw note text or raw detected `PHISpan.text`;
- audit CSVs are internal review artifacts, not de-identified training outputs.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

from .audit import (
    AUDIT_COLUMNS,
    _format_row_warning,
    _span_to_audit_row,
    _write_warning_audit_row,
)
from .note import deidentify_note


def deidentify_csv(
    input_file,
    output_file,
    *,
    audit_output_file=None,
    note_text_column="note_text",
    patient_id_column="patient_id",
    encounter_id_column="encounter_id",
    note_id_column="note_id",
    types=None,
    custom_dr_first_names=None,
    custom_dr_last_names=None,
    custom_patient_first_names=None,
    custom_patient_last_names=None,
    encoding="utf-8",
    stable_date_shift: bool = False,
    date_shift_secret: str | bytes | None = None,
    date_shift_secret_env_var: str | None = None,
    date_shift_days: int = 45,
    stable_patient_name_surrogates: bool = False,
    patient_aliases_by_patient_id: dict[str, Iterable[str]] | None = None,
    patient_name_secret: str | bytes | None = None,
    patient_name_secret_env_var: str | None = None,
    custom_regexes=None,
    protected_clinical_terms=None,
    include_builtin_protected_clinical_terms: bool = True,
):
    """De-identify a CSV by applying `deidentify_note(...)` row by row.

    The configured note-text column is replaced with the final de-identified
    text for successful rows. All other columns are copied unchanged. Rows that
    fail are omitted from the output CSV and recorded in the returned summary
    and optional audit CSV.

    Args:
        input_file: Input CSV path or path-like object.
        output_file: Output CSV path or path-like object for de-identified rows.
        audit_output_file: Optional audit CSV path. When provided, one audit row
            is written per emitted span, plus warning-only rows for row failures
            and note-level warnings.
        note_text_column: Name of the CSV column containing note text to
            de-identify. This column must exist.
        patient_id_column: Optional patient ID column name. If the column exists,
            its value is passed to `deidentify_note(...)` and copied into span
            metadata.
        encounter_id_column: Optional encounter ID column name. If the column
            exists, its value is passed through as metadata.
        note_id_column: Optional note ID column name. If the column exists, its
            value is passed through as metadata.
        types: pyDeid PHI categories to request for each row.
        custom_dr_first_names: Extra doctor first-name tokens passed to pyDeid.
        custom_dr_last_names: Extra doctor last-name tokens passed to pyDeid.
        custom_patient_first_names: Extra patient first-name tokens passed to
            pyDeid.
        custom_patient_last_names: Extra patient last-name tokens passed to
            pyDeid.
        encoding: File encoding used for input, output, and audit CSV files.
        stable_date_shift: Whether to enable deterministic per-patient date
            shifting.
        date_shift_secret: Direct secret for date shifting. Useful for tests;
            environment variables are preferred for runtime use.
        date_shift_secret_env_var: Environment variable containing the date-shift
            secret. Used only when `date_shift_secret` is not provided.
        date_shift_days: Inclusive maximum date-shift range. For example, `45`
            maps each patient to an offset in `[-45, +45]`.
        stable_patient_name_surrogates: Whether explicitly configured patient
            aliases should receive deterministic fake patient names.
        patient_aliases_by_patient_id: Mapping from patient ID to explicit
            aliases for that patient. Required when stable patient-name
            surrogates are enabled.
        patient_name_secret: Direct secret for stable patient-name generation.
            Useful for tests; environment variables are preferred for runtime use.
        patient_name_secret_env_var: Environment variable containing the
            patient-name secret. Used only when `patient_name_secret` is not
            provided.
        custom_regexes: ProjectPHI custom regex config. ProjectPHI validates and
            converts this config, while pyDeid performs the actual matching.
        protected_clinical_terms: Runtime protected-term config used as a
            span-local false-positive veto.
        include_builtin_protected_clinical_terms: Whether to include the curated
            built-in protected clinical terminology list.

    Returns:
        Summary dictionary with:
        - `rows_read`: number of input data rows processed;
        - `rows_written`: number of successful rows written to output;
        - `rows_failed`: number of failed rows omitted from output;
        - `spans_written`: number of span audit rows written;
        - `warnings`: sanitized row-failure and row-warning messages.

    Raises:
        ValueError: If input/output/audit paths overlap, if the note-text column
            is missing, or if required row-level stable patient-name inputs are
            missing.

    Examples:
        Basic CSV de-identification:
            summary = deidentify_csv(
                "notes.csv",
                "notes_deidentified.csv",
                note_text_column="note_text",
            )

        With audit output:
            summary = deidentify_csv(
                "notes.csv",
                "notes_deidentified.csv",
                audit_output_file="notes_audit.csv",
            )

        With stable date shifting:
            summary = deidentify_csv(
                "notes.csv",
                "notes_deidentified.csv",
                patient_id_column="patient_id",
                stable_date_shift=True,
                date_shift_secret_env_var="PROJECTPHI_DATE_SHIFT_SECRET",
                date_shift_days=45,
            )

        With stable patient-name aliases:
            summary = deidentify_csv(
                "notes.csv",
                "notes_deidentified.csv",
                patient_id_column="patient_id",
                stable_patient_name_surrogates=True,
                patient_aliases_by_patient_id={
                    "P001": ["Jane Smith", "Jane", "Ms Smith"],
                },
                patient_name_secret_env_var="PROJECTPHI_PATIENT_NAME_SECRET",
            )
    """
    input_path = Path(input_file)
    output_path = Path(output_file)
    resolved_input_path = input_path.resolve()
    resolved_output_path = output_path.resolve()
    # Avoid reading and writing the same file. This prevents accidental
    # destruction of the source CSV and keeps audit output separate.
    if resolved_input_path == resolved_output_path:
        raise ValueError("input_file and output_file must not be the same path.")
    if audit_output_file is not None:
        resolved_audit_path = Path(audit_output_file).resolve()
        if resolved_audit_path == resolved_input_path:
            raise ValueError("audit_output_file and input_file must not be the same path.")
        if resolved_audit_path == resolved_output_path:
            raise ValueError("audit_output_file and output_file must not be the same path.")

    # The summary intentionally stores counts plus sanitized warning strings
    # only. It should not contain raw note text or arbitrary exception messages.
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
        # Create the audit file first when requested so span/warning rows can be
        # streamed as each input row is processed.
        if audit_output_file is not None:
            audit_handle = open(audit_output_file, "w", newline="", encoding=encoding)
            audit_writer = csv.DictWriter(audit_handle, fieldnames=AUDIT_COLUMNS)
            audit_writer.writeheader()

        with open(input_path, newline="", encoding=encoding) as input_handle:
            reader = csv.DictReader(input_handle)
            fieldnames = reader.fieldnames or []
            # Validate the required note-text column before writing output rows.
            # Optional ID columns are read only when present.
            if note_text_column not in fieldnames:
                raise ValueError(
                    f"Required note text column {note_text_column!r} not found in input CSV."
                )

            with open(output_path, "w", newline="", encoding=encoding) as output_handle:
                writer = csv.DictWriter(output_handle, fieldnames=fieldnames)
                writer.writeheader()

                for row_number, row in enumerate(reader, start=2):
                    summary["rows_read"] += 1
                    patient_id = _optional_row_value(row, fieldnames, patient_id_column)
                    encounter_id = _optional_row_value(row, fieldnames, encounter_id_column)
                    note_id = _optional_row_value(row, fieldnames, note_id_column)

                    try:
                        # Resolve row-specific aliases before calling the single-note
                        # workflow. Missing aliases fail this row rather than causing
                        # guessed patient-name replacement.
                        patient_aliases = _patient_aliases_for_row(
                            patient_id,
                            patient_aliases_by_patient_id,
                            stable_patient_name_surrogates=stable_patient_name_surrogates,
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
                            stable_patient_name_surrogates=stable_patient_name_surrogates,
                            patient_aliases=patient_aliases,
                            patient_name_secret=patient_name_secret,
                            patient_name_secret_env_var=patient_name_secret_env_var,
                            custom_regexes=custom_regexes,
                            protected_clinical_terms=protected_clinical_terms,
                            include_builtin_protected_clinical_terms=(
                                include_builtin_protected_clinical_terms
                            ),
                        )
                    except Exception as exc:
                        # Omit failed rows and emit sanitized context only. Do
                        # not copy raw notes or arbitrary exception text into
                        # the output summary or audit CSV.
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

                    # Preserve the original row shape and replace only the
                    # configured note-text column.
                    output_row = dict(row)
                    output_row[note_text_column] = result.deidentified_text
                    writer.writerow(output_row)
                    summary["rows_written"] += 1

                    # Audit rows are internal review artifacts. They include offsets and
                    # replacement metadata, but not raw span text.
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


def _optional_row_value(
    row: dict[str, Any],
    fieldnames: list[str],
    column: str,
) -> str | None:
    """Return a row value only when the optional column exists.

    Optional ID columns are not required in every CSV. When the configured
    column is absent from the header, this returns `None` instead of failing.

    Args:
        row: Current CSV row from `csv.DictReader`.
        fieldnames: Input CSV header names.
        column: Optional column name to read.

    Returns:
        The row value when the column exists, otherwise `None`.
    """
    if column in fieldnames:
        return row.get(column)
    return None


def _patient_aliases_for_row(
    patient_id: str | None,  # Row patient ID used as alias key.
    patient_aliases_by_patient_id: dict[str, Iterable[str]] | None,  # Alias manifest mapping.
    *,
    stable_patient_name_surrogates: bool,  # Whether aliases are required.
) -> Iterable[str] | None:
    """Return explicit aliases for one row's patient-name policy.

    Stable patient-name surrogates require explicit aliases keyed by the row's
    patient ID. Missing IDs or aliases raise `ValueError`, which the CSV loop
    handles as a sanitized row failure. The affected row is omitted rather than
    processed with guessed patient-name identity.

    Args:
        patient_id: Patient ID from the current row, if available.
        patient_aliases_by_patient_id: Mapping from patient ID to explicit
            aliases for that patient.
        stable_patient_name_surrogates: Whether row aliases are required.

    Returns:
        Aliases for the row's patient, or `None` when stable patient-name
        surrogates are disabled.

    Raises:
        ValueError: If stable patient-name surrogates are enabled but the row has
            no patient ID, no alias mapping, or no aliases for that patient.

    Example:
        patient_aliases_by_patient_id = {
            "P001": ["Jane Smith", "Jane", "Ms Smith"],
        }

        A row with `patient_id == "P001"` receives those aliases. A row with
        `patient_id == "P999"` fails instead of guessing aliases.
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
