"""Load small runtime configuration files for the CSV pipeline.

These helpers parse operator-supplied config files into the in-memory shapes
already accepted by `deidentify_csv(...)`.

They do not:
- detect PHI;
- infer aliases from notes;
- run regex matching over note text;
- scan notes for protected terms.

Supported config files:
- patient alias manifest CSV: `patient_id,alias`
- custom regex JSON: rule ID -> `phi_type`, `pattern`, optional `replacement`
- protected clinical terms CSV: `rule_id,category,term`

Security notes:
- validation errors use row numbers and generic messages;
- raw regex patterns are not echoed in custom-regex validation errors;
- protected term lists are not printed during validation;
- these loaders should be treated as config ingestion, not de-identification.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .custom_regex import _build_pydeid_custom_regexes
from .protected_terms import _build_protected_terms_profile


def load_patient_alias_manifest(
    path,
    *,
    encoding="utf-8",
) -> dict[str, list[str]]:
    """Load a patient-alias manifest CSV.

    Expected CSV columns:
        patient_id,alias

    Example:
        patient_id,alias
        P001,Jane Smith
        P001,Jane
        P001,Ms Smith
        P002,Robert Chen

    Returns:
        Dictionary mapping each patient ID to aliases in file order:

        {
            "P001": ["Jane Smith", "Jane", "Ms Smith"],
            "P002": ["Robert Chen"],
        }

    Behavior:
        - trims surrounding whitespace from `patient_id` and `alias`;
        - skips fully blank rows;
        - preserves alias order per patient;
        - does not infer aliases, validate whether aliases are real names, or
          perform entity resolution.

    Raises:
        ValueError: If required columns are missing, or if a nonblank row has an
        empty `patient_id` or `alias`.

    Notes:
        Error messages identify row numbers but do not include alias values.
    """

    aliases_by_patient_id: dict[str, list[str]] = {}
    with open(Path(path), newline="", encoding=encoding) as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required_columns = {"patient_id", "alias"}
        missing_columns = sorted(required_columns.difference(fieldnames))
        # Keep the error generic. Column names are safe, but the exact file
        # contents are not needed for diagnosis.
        if missing_columns:
            raise ValueError("Alias manifest is missing required columns.")

        for row_number, row in enumerate(reader, start=2):
            # Blank rows are ignored so operators can leave spacing in small
            # manually edited manifests.
            if _blank_csv_row(row):
                continue
            patient_id = (row.get("patient_id") or "").strip()
            alias = (row.get("alias") or "").strip()
            if not patient_id:
                raise ValueError(f"Alias manifest row {row_number} has an empty patient_id.")
            if not alias:
                raise ValueError(f"Alias manifest row {row_number} has an empty alias.")
            aliases_by_patient_id.setdefault(patient_id, []).append(alias)

    return aliases_by_patient_id


def load_custom_regexes_json(
    path,
    *,
    encoding="utf-8",
) -> dict:
    """Load and validate ProjectPHI custom-regex JSON.

    Expected JSON shape:
        {
          "synthetic_wb_mrn": {
            "phi_type": "Synthetic WB MRN",
            "pattern": "\\\\bWB-\\\\d{7}\\\\b",
            "replacement": "<SYNTHETIC_MRN>"
          }
        }

    The loaded object is returned unchanged after validation. It can be passed
    directly to `deidentify_csv(..., custom_regexes=...)`.

    Validation:
        This reuses `_build_pydeid_custom_regexes(...)`, the same production
        converter used by the de-identification workflow. That validates the
        config shape and regex syntax, but does not run regex matching over note
        text.

    Raises:
        ValueError: If the file is invalid JSON, if the top-level JSON value is
        not an object, or if the custom-regex config is invalid.

    Security notes:
        Raw regex patterns may describe local identifier formats. Validation
        errors should not echo them.
    """

    try:
        with open(Path(path), encoding=encoding) as handle:
            custom_regexes = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError("Custom regex JSON is invalid.") from exc

    if not isinstance(custom_regexes, dict):
        raise ValueError("Custom regex JSON must contain a top-level object.")

    # Reuse the production config validator/converter, then discard pyDeid
    # objects. This validates shape and regex syntax without scanning notes.
    _build_pydeid_custom_regexes(custom_regexes)
    return custom_regexes


def load_protected_clinical_terms_csv(
    path,
    *,
    encoding="utf-8",
) -> dict:
    """Load protected clinical terms from CSV.

    Expected CSV columns:
        rule_id,category,term

    Example:
        rule_id,category,term
        birads,breast_imaging,BI-RADS 2
        birads,breast_imaging,BI-RADS 3
        pathology,breast_pathology,ductal carcinoma in situ

    Returns:
        Runtime dictionary accepted by `deidentify_csv(...)`:

        {
            "birads": {
                "category": "breast_imaging",
                "terms": ["BI-RADS 2", "BI-RADS 3"],
            },
            "pathology": {
                "category": "breast_pathology",
                "terms": ["ductal carcinoma in situ"],
            },
        }

    Behavior:
        - trims surrounding whitespace from `rule_id`, `category`, and `term`;
        - skips fully blank rows;
        - preserves term order within each rule;
        - requires a rule ID to keep the same category across all its rows;
        - validates duplicate normalized terms through the production protected
          terms profile builder.

    Raises:
        ValueError: If required columns are missing, a nonblank row has an empty
        field, a rule ID changes category, or protected-term validation fails.

    Notes:
        Protected terms are semantic-preservation vetoes, not PHI detectors.
        This loader does not scan note text.
    """

    protected_terms: dict[str, dict[str, Any]] = {}
    with open(Path(path), newline="", encoding=encoding) as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required_columns = {"rule_id", "category", "term"}
        missing_columns = sorted(required_columns.difference(fieldnames))
        if missing_columns:
            raise ValueError("Protected clinical terms CSV is missing required columns.")

        for row_number, row in enumerate(reader, start=2):
            if _blank_csv_row(row):
                continue
            rule_id = (row.get("rule_id") or "").strip()
            category = (row.get("category") or "").strip()
            term = (row.get("term") or "").strip()
            if not rule_id:
                raise ValueError(
                    f"Protected clinical terms CSV row {row_number} has an empty rule_id."
                )
            if not category:
                raise ValueError(
                    f"Protected clinical terms CSV row {row_number} has an empty category."
                )
            if not term:
                raise ValueError(
                    f"Protected clinical terms CSV row {row_number} has an empty term."
                )

            rule_config = protected_terms.setdefault(
                rule_id,
                {"category": category, "terms": []},
            )
            if rule_config["category"] != category:
                raise ValueError(
                    f"Protected clinical terms CSV row {row_number} changes category for rule_id."
                )
            rule_config["terms"].append(term)

    _build_protected_terms_profile(
        protected_terms,
        include_builtin_protected_clinical_terms=False,
    )
    return protected_terms


def _blank_csv_row(
    row: dict[str, Any],
) -> bool:
    """Return whether a parsed CSV row is fully blank.

    A row is considered blank when every parsed field is empty after converting
    `None` to an empty string and trimming whitespace.

    Examples:
        {"patient_id": "", "alias": ""} -> True
        {"patient_id": "   ", "alias": None} -> True
        {"patient_id": "P001", "alias": ""} -> False
    """
    return all(not str(value or "").strip() for value in row.values())
