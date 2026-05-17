"""Minimal command-line interface for CSV de-identification.

The CLI is a thin adapter around `deidentify_csv(...)`. It loads small runtime
config files, validates required flag combinations, runs the CSV pipeline, and
prints sanitized summary counts/warnings.

It deliberately does not:
- call pyDeid directly;
- accept direct secret values on the command line;
- print notes, aliases, regex patterns, detected PHI, or arbitrary exception text.

Secrets must be supplied through environment variables and referenced by name
with CLI flags.

Examples:
    Basic CSV de-identification:
        project-phi-deid input.csv output.csv

    With audit output:
        project-phi-deid input.csv output.csv \\
            --audit-output-file audit.csv

    With stable date shifting:
        export PROJECTPHI_DATE_SHIFT_SECRET="runtime-secret"
        project-phi-deid input.csv output.csv \\
            --stable-date-shift \\
            --date-shift-secret-env-var PROJECTPHI_DATE_SHIFT_SECRET

    With stable patient-name aliases:
        export PROJECTPHI_PATIENT_NAME_SECRET="runtime-secret"
        project-phi-deid input.csv output.csv \\
            --stable-patient-name-surrogates \\
            --patient-alias-manifest aliases.csv \\
            --patient-name-secret-env-var PROJECTPHI_PATIENT_NAME_SECRET

    With custom regexes and protected terms:
        project-phi-deid input.csv output.csv \\
            --custom-regex-json custom_regexes.json \\
            --protected-clinical-terms-csv protected_terms.csv

Exit codes:
    0: CLI ran successfully, even if some CSV rows failed and were reported in
       the sanitized summary.
    2: argument/config/file error.
    1: unexpected de-identification failure.
"""

from __future__ import annotations

import argparse
import sys

from .config_loaders import (
    load_custom_regexes_json,
    load_patient_alias_manifest,
    load_protected_clinical_terms_csv,
)
from .csv_adapter import deidentify_csv


def main(
    argv: list[str] | None = None,
) -> int:
    """Run the CLI and return a process-style exit code.

    Args:
        argv: Optional argument list for tests. When `None`, argparse reads from
            `sys.argv`.

    Returns:
        Process-style exit code:
        - `0` for successful CLI execution;
        - `2` for argument, config-loading, or file-operation errors;
        - `1` for unexpected de-identification failures.

    Notes:
        Row-level de-identification failures are reported in the returned
        summary from `deidentify_csv(...)`. They do not make the CLI exit
        nonzero by themselves, because the CSV adapter may still write successful
        rows and warning-only audit rows.
    """
    # Validate flag combinations before loading files or running de-identification.
    # The CLI accepts environment variable names for secrets, not secret values.
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.stable_date_shift and not args.date_shift_secret_env_var:
        return _argument_error("--stable-date-shift requires --date-shift-secret-env-var")
    if args.stable_patient_name_surrogates and not args.patient_alias_manifest:
        return _argument_error("--stable-patient-name-surrogates requires --patient-alias-manifest")
    if args.stable_patient_name_surrogates and not args.patient_name_secret_env_var:
        return _argument_error("--stable-patient-name-surrogates requires --patient-name-secret-env-var")

    # Load optional config files into the in-memory shapes expected by
    # `deidentify_csv(...)`. Loaders validate shape but do not scan notes.
    try:
        patient_aliases_by_patient_id = (
            load_patient_alias_manifest(args.patient_alias_manifest, encoding=args.encoding)
            if args.patient_alias_manifest
            else None
        )
        custom_regexes = (
            load_custom_regexes_json(args.custom_regex_json, encoding=args.encoding)
            if args.custom_regex_json
            else None
        )
        protected_clinical_terms = (
            load_protected_clinical_terms_csv(
                args.protected_clinical_terms_csv,
                encoding=args.encoding,
            )
            if args.protected_clinical_terms_csv
            else None
        )
        summary = deidentify_csv(
            args.input_csv,
            args.output_csv,
            audit_output_file=args.audit_output_file,
            note_text_column=args.note_text_column,
            patient_id_column=args.patient_id_column,
            encounter_id_column=args.encounter_id_column,
            note_id_column=args.note_id_column,
            encoding=args.encoding,
            stable_date_shift=args.stable_date_shift,
            date_shift_secret_env_var=args.date_shift_secret_env_var,
            date_shift_days=args.date_shift_days,
            stable_patient_name_surrogates=args.stable_patient_name_surrogates,
            patient_aliases_by_patient_id=patient_aliases_by_patient_id,
            patient_name_secret_env_var=args.patient_name_secret_env_var,
            custom_regexes=custom_regexes,
            protected_clinical_terms=protected_clinical_terms,
        )
    # Keep error messages sanitized. ValueError messages from project
    # validators are written to be safe; arbitrary exception text is not.
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Error: file operation failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    except Exception as exc:
        # Do not echo arbitrary exception text; it could contain raw note text or
        # config details from lower layers.
        print(f"Error: de-identification failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    _print_summary(summary)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser.

    This function only defines flags. It does not read files, inspect
    environment variables, or run de-identification.

    Positional arguments:
        input_csv: Source CSV file.
        output_csv: Destination CSV file for successful de-identified rows.

    Important flags:
        --audit-output-file: Optional internal audit CSV path.
        --note-text-column: Input column containing note text. Defaults to
            `note_text`.
        --stable-date-shift: Enables deterministic per-patient date shifting.
            Requires `--date-shift-secret-env-var`.
        --stable-patient-name-surrogates: Enables deterministic fake patient
            names for explicit aliases. Requires `--patient-alias-manifest` and
            `--patient-name-secret-env-var`.
        --custom-regex-json: Optional ProjectPHI custom regex config.
        --protected-clinical-terms-csv: Optional protected clinical term config.
    """
    parser = argparse.ArgumentParser(
        prog="project-phi-deid",
        description="Run the ProjectPHI CSV de-identification pipeline.",
    )
    parser.add_argument("input_csv")
    parser.add_argument("output_csv")
    parser.add_argument("--audit-output-file")
    parser.add_argument("--note-text-column", default="note_text")
    parser.add_argument("--patient-id-column", default="patient_id")
    parser.add_argument("--encounter-id-column", default="encounter_id")
    parser.add_argument("--note-id-column", default="note_id")
    parser.add_argument("--stable-date-shift", action="store_true")
    parser.add_argument("--date-shift-secret-env-var")
    parser.add_argument("--date-shift-days", type=int, default=45)
    parser.add_argument("--stable-patient-name-surrogates", action="store_true")
    parser.add_argument("--patient-alias-manifest")
    parser.add_argument("--patient-name-secret-env-var")
    parser.add_argument("--custom-regex-json")
    parser.add_argument("--protected-clinical-terms-csv")
    parser.add_argument("--encoding", default="utf-8")
    return parser


def _print_summary(
    summary: dict,
) -> None:
    """Print sanitized CSV pipeline summary output.

    Printed fields:
        rows_read: Number of input data rows processed.
        rows_written: Number of successful rows written to output.
        rows_failed: Number of failed rows omitted from output.
        spans_written: Number of span audit rows written.
        warnings: Count of sanitized warnings.
        warning: One line per sanitized warning.

    Notes:
        The summary should contain counts and sanitized warning strings only. It
        should not include raw note text, detected PHI, aliases, regex patterns,
        secrets, hashes, or arbitrary exception messages.
    """
    print(f"rows_read={summary.get('rows_read', 0)}")
    print(f"rows_written={summary.get('rows_written', 0)}")
    print(f"rows_failed={summary.get('rows_failed', 0)}")
    print(f"spans_written={summary.get('spans_written', 0)}")
    warnings = summary.get("warnings") or []
    print(f"warnings={len(warnings)}")
    for warning in warnings:
        print(f"warning={warning}")


def _argument_error(
    message: str,
) -> int:
    """Print a sanitized CLI argument error and return exit code 2.

    Args:
        message: Static/sanitized validation message. It should not contain raw
            note text, config contents, secrets, regex patterns, or PHI.

    Returns:
        `2`, matching common CLI usage/configuration error behavior.
    """
    print(f"Error: {message}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
