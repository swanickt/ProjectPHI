"""Minimal command-line interface for CSV de-identification.

The CLI is a thin adapter around `deidentify_csv(...)`. It loads small runtime
config files, validates required flag combinations, and prints only sanitized
summary counts/warnings. It does not accept direct secret values on the command
line and does not print notes, aliases, regex patterns, or detected PHI.
"""

from __future__ import annotations

import argparse
import sys

from .config_loaders import (
    load_custom_regexes_json,
    load_patient_alias_manifest,
    load_provider_alias_manifest,
    load_protected_clinical_terms_csv,
)
from .csv_adapter import deidentify_csv


def main(
    argv: list[str] | None = None,  # Optional argv override for tests.
) -> int:
    """Run the CLI and return a process-style exit code.

    `argv` is injectable for tests. Row-level de-identification failures remain
    part of the returned summary and do not make the CLI exit nonzero; argument,
    config-loading, and file-operation failures return nonzero codes.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.stable_date_shift and not args.date_shift_secret_env_var:
        return _argument_error("--stable-date-shift requires --date-shift-secret-env-var")
    if args.stable_patient_name_surrogates and not args.patient_alias_manifest:
        return _argument_error("--stable-patient-name-surrogates requires --patient-alias-manifest")
    if args.stable_patient_name_surrogates and not args.patient_name_secret_env_var:
        return _argument_error("--stable-patient-name-surrogates requires --patient-name-secret-env-var")
    if args.stable_provider_name_surrogates and not args.provider_alias_manifest:
        return _argument_error("--stable-provider-name-surrogates requires --provider-alias-manifest")
    if args.stable_provider_name_surrogates and not args.provider_name_secret_env_var:
        return _argument_error("--stable-provider-name-surrogates requires --provider-name-secret-env-var")
    if args.stable_unknown_name_surrogates and not args.unknown_name_secret_env_var:
        return _argument_error("--stable-unknown-name-surrogates requires --unknown-name-secret-env-var")

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
        provider_aliases_by_provider_id = (
            load_provider_alias_manifest(args.provider_alias_manifest, encoding=args.encoding)
            if args.provider_alias_manifest
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
            shift_partial_month_day_dates=args.shift_partial_month_day_dates,
            stable_patient_name_surrogates=args.stable_patient_name_surrogates,
            patient_aliases_by_patient_id=patient_aliases_by_patient_id,
            patient_name_secret_env_var=args.patient_name_secret_env_var,
            stable_provider_name_surrogates=args.stable_provider_name_surrogates,
            provider_aliases_by_provider_id=provider_aliases_by_provider_id,
            provider_name_secret_env_var=args.provider_name_secret_env_var,
            stable_unknown_name_surrogates=args.stable_unknown_name_surrogates,
            unknown_name_secret_env_var=args.unknown_name_secret_env_var,
            custom_regexes=custom_regexes,
            protected_clinical_terms=protected_clinical_terms,
        )
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
    """Create the argument parser without reading files or environment values."""
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
    parser.add_argument(
        "--shift-partial-month-day-dates",
        action="store_true",
        default=True,
    )
    parser.add_argument(
        "--no-shift-partial-month-day-dates",
        action="store_false",
        dest="shift_partial_month_day_dates",
    )
    parser.add_argument("--stable-patient-name-surrogates", action="store_true")
    parser.add_argument("--patient-alias-manifest")
    parser.add_argument("--patient-name-secret-env-var")
    parser.add_argument("--stable-provider-name-surrogates", action="store_true")
    parser.add_argument("--provider-alias-manifest")
    parser.add_argument("--provider-name-secret-env-var")
    parser.add_argument("--stable-unknown-name-surrogates", action="store_true")
    parser.add_argument("--unknown-name-secret-env-var")
    parser.add_argument("--custom-regex-json")
    parser.add_argument("--protected-clinical-terms-csv")
    parser.add_argument("--encoding", default="utf-8")
    return parser


def _print_summary(
    summary: dict,  # Sanitized deidentify_csv summary dictionary.
) -> None:
    """Print sanitized summary counts and already-sanitized row warnings."""
    print(f"rows_read={summary.get('rows_read', 0)}")
    print(f"rows_written={summary.get('rows_written', 0)}")
    print(f"rows_failed={summary.get('rows_failed', 0)}")
    print(f"spans_written={summary.get('spans_written', 0)}")
    warnings = summary.get("warnings") or []
    print(f"warnings={len(warnings)}")
    for warning in warnings:
        print(f"warning={warning}")


def _argument_error(
    message: str,  # Sanitized CLI validation message.
) -> int:
    """Print a sanitized argument error and return the CLI usage-error code."""
    print(f"Error: {message}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
