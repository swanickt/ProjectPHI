"""
Run the 30-note synthetic ProjectPHI smoke test
"""

from __future__ import annotations

import json
from pathlib import Path

from project_phi import deidentify_csv
from project_phi.config_loaders import (
    load_custom_regexes_json,
    load_patient_alias_manifest,
    load_provider_alias_manifest,
)


BASE_DIR = Path(__file__).resolve().parent


def _load_custom_doctor_names(path: Path) -> tuple[set[str], set[str]]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    first_names = {str(value).strip() for value in data.get("custom_dr_first_names", [])}
    last_names = {str(value).strip() for value in data.get("custom_dr_last_names", [])}
    return {value for value in first_names if value}, {value for value in last_names if value}


def main() -> int:
    custom_dr_first_names, custom_dr_last_names = _load_custom_doctor_names(
        BASE_DIR / "custom_doctor_names.json"
    )
    summary = deidentify_csv(
        BASE_DIR / "input_notes.csv",
        BASE_DIR / "deidentified_output.csv",
        audit_output_file=BASE_DIR / "audit_output.csv",
        stable_date_shift=True,
        date_shift_secret_env_var="PROJECT_PHI_DATE_SHIFT_SECRET",
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id=load_patient_alias_manifest(BASE_DIR / "patient_aliases.csv"),
        patient_name_secret_env_var="PROJECT_PHI_PATIENT_NAME_SECRET",
        stable_provider_name_surrogates=True,
        provider_aliases_by_provider_id=load_provider_alias_manifest(
            BASE_DIR / "provider_aliases.csv"
        ),
        provider_name_secret_env_var="PROJECT_PHI_PROVIDER_NAME_SECRET",
        custom_regexes=load_custom_regexes_json(BASE_DIR / "custom_regexes.json"),
        custom_dr_first_names=custom_dr_first_names,
        custom_dr_last_names=custom_dr_last_names,
    )

    print(f"rows_read={summary.get('rows_read', 0)}")
    print(f"rows_written={summary.get('rows_written', 0)}")
    print(f"rows_failed={summary.get('rows_failed', 0)}")
    print(f"spans_written={summary.get('spans_written', 0)}")
    warnings = summary.get("warnings") or []
    print(f"warnings={len(warnings)}")
    for warning in warnings:
        print(f"warning={warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
