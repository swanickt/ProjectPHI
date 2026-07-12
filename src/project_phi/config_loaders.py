"""Load small runtime configuration files for the CSV pipeline.

These helpers parse operator-supplied config into the in-memory shapes already
accepted by `deidentify_csv(...)`. They do not detect PHI, infer aliases, or
run regex matching over notes.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .custom_regex import _build_pydeid_custom_regexes
from .patient_names import _normalize_patient_name_style
from .protected_terms import _build_protected_terms_profile


def load_patient_alias_manifest(
    path,  # CSV path with patient_id,alias columns.
    *,
    encoding="utf-8",  # File encoding for the manifest.
) -> dict[str, list[str]]:
    """Load `patient_id,alias` CSV into the alias mapping used by CSV runs.

    Returns `dict[patient_id, list[alias]]`, preserving row order per patient.
    The loader trims whitespace, skips blank rows, and rejects missing columns
    or empty values with row-number-only errors. It does not infer aliases,
    validate whether aliases are real names, or perform entity resolution.
    """

    aliases_by_patient_id: dict[str, list[str]] = {}
    with open(Path(path), newline="", encoding=encoding) as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required_columns = {"patient_id", "alias"}
        missing_columns = sorted(required_columns.difference(fieldnames))
        if missing_columns:
            raise ValueError("Alias manifest is missing required columns.")

        for row_number, row in enumerate(reader, start=2):
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


def load_patient_alias_manifest_with_styles(
    path,  # CSV path with patient_id,alias and optional name_style columns.
    *,
    encoding="utf-8",  # File encoding for the manifest.
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Load patient aliases plus optional explicit fake-name styles.

    The required columns remain `patient_id` and `alias`; `name_style` is
    optional and may contain `feminine`, `masculine`, or `neutral`. Missing or
    neutral style preserves the default fake-name behavior. Non-empty
    styles must be consistent for every row with the same `patient_id`.
    """

    aliases_by_patient_id: dict[str, list[str]] = {}
    styles_by_patient_id: dict[str, str] = {}
    with open(Path(path), newline="", encoding=encoding) as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required_columns = {"patient_id", "alias"}
        missing_columns = sorted(required_columns.difference(fieldnames))
        if missing_columns:
            raise ValueError("Alias manifest is missing required columns.")

        for row_number, row in enumerate(reader, start=2):
            if _blank_csv_row(row):
                continue
            patient_id = (row.get("patient_id") or "").strip()
            alias = (row.get("alias") or "").strip()
            if not patient_id:
                raise ValueError(f"Alias manifest row {row_number} has an empty patient_id.")
            if not alias:
                raise ValueError(f"Alias manifest row {row_number} has an empty alias.")
            aliases_by_patient_id.setdefault(patient_id, []).append(alias)

            try:
                style = _normalize_patient_name_style(row.get("name_style"))
            except ValueError as exc:
                raise ValueError(
                    f"Alias manifest row {row_number} has invalid name_style."
                ) from exc
            if style is None:
                continue
            previous_style = styles_by_patient_id.get(patient_id)
            if previous_style is not None and previous_style != style:
                raise ValueError(
                    f"Alias manifest row {row_number} has conflicting name_style."
                )
            styles_by_patient_id[patient_id] = style

    return aliases_by_patient_id, styles_by_patient_id


def load_provider_alias_manifest(
    path,  # CSV path with provider_id,alias columns.
    *,
    encoding="utf-8",  # File encoding for the manifest.
) -> dict[str, list[str]]:
    """Load `provider_id,alias` CSV into the provider alias mapping.

    The loader preserves alias order per provider and performs only shape
    validation. It does not infer aliases, validate real provider identities, or
    echo raw aliases in validation errors.
    """
    aliases_by_provider_id: dict[str, list[str]] = {}
    with open(Path(path), newline="", encoding=encoding) as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required_columns = {"provider_id", "alias"}
        missing_columns = sorted(required_columns.difference(fieldnames))
        if missing_columns:
            raise ValueError("Provider alias manifest is missing required columns.")

        for row_number, row in enumerate(reader, start=2):
            if _blank_csv_row(row):
                continue
            provider_id = (row.get("provider_id") or "").strip()
            alias = (row.get("alias") or "").strip()
            if not provider_id:
                raise ValueError(
                    f"Provider alias manifest row {row_number} has an empty provider_id."
                )
            if not alias:
                raise ValueError(f"Provider alias manifest row {row_number} has an empty alias.")
            aliases_by_provider_id.setdefault(provider_id, []).append(alias)

    return aliases_by_provider_id


def load_custom_regexes_json(
    path,  # JSON path containing project custom regex config.
    *,
    encoding="utf-8",  # File encoding for the JSON file.
) -> dict:
    """Load project custom-regex JSON and validate its shape.

    The expected shape is the same dictionary accepted by `deidentify_csv(...)`:
    project rule ID -> `phi_type`, `pattern`, and optional `replacement`.
    Validation reuses the production custom-regex converter but does not run
    regex matching over any note text. Raw regex patterns are not included in
    validation errors.
    """

    try:
        with open(Path(path), encoding=encoding) as handle:
            custom_regexes = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError("Custom regex JSON is invalid.") from exc

    if not isinstance(custom_regexes, dict):
        raise ValueError("Custom regex JSON must contain a top-level object.")

    # Reuse the production config validator/converter, then discard pyDeid
    # objects. This validates shape without running project regex matching.
    _build_pydeid_custom_regexes(custom_regexes)
    return custom_regexes


def load_protected_clinical_terms_csv(
    path,  # CSV path with rule_id,category,term columns.
    *,
    encoding="utf-8",  # File encoding for the terms CSV.
) -> dict:
    """Load protected clinical terms from CSV.

    Required columns are `rule_id` and `category`. Rows may provide a whole-span
    `term`, or a protected `component` plus `within_phrase` for risky eponyms
    that should only be preserved inside an approved clinical phrase.

    Returns the runtime dictionary accepted by `deidentify_csv(...)`. Terms are
    operator-supplied false-positive vetoes, not PHI detectors. The loader
    keeps rule order, rejects missing/empty fields with sanitized row-number
    errors, and validates duplicate normalized terms through the production
    profile builder without printing term lists.
    """

    protected_terms: dict[str, dict[str, Any]] = {}
    with open(Path(path), newline="", encoding=encoding) as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required_columns = {"rule_id", "category"}
        missing_columns = sorted(required_columns.difference(fieldnames))
        if missing_columns:
            raise ValueError("Protected clinical terms CSV is missing required columns.")
        has_term_column = "term" in fieldnames
        has_component_columns = {"component", "within_phrase"}.issubset(fieldnames)
        if not has_term_column and not has_component_columns:
            raise ValueError(
                "Protected clinical terms CSV requires term or component columns."
            )

        for row_number, row in enumerate(reader, start=2):
            if _blank_csv_row(row):
                continue
            rule_id = (row.get("rule_id") or "").strip()
            category = (row.get("category") or "").strip()
            term = (row.get("term") or "").strip()
            component = (row.get("component") or "").strip()
            within_phrase = (row.get("within_phrase") or "").strip()
            if not rule_id:
                raise ValueError(
                    f"Protected clinical terms CSV row {row_number} has an empty rule_id."
                )
            if not category:
                raise ValueError(
                    f"Protected clinical terms CSV row {row_number} has an empty category."
                )
            if not term and not (component and within_phrase):
                raise ValueError(
                    f"Protected clinical terms CSV row {row_number} has no protected value."
                )
            if bool(component) != bool(within_phrase):
                raise ValueError(
                    f"Protected clinical terms CSV row {row_number} has incomplete component data."
                )

            rule_config = protected_terms.setdefault(
                rule_id,
                {"category": category, "terms": [], "component_terms": []},
            )
            if rule_config["category"] != category:
                raise ValueError(
                    f"Protected clinical terms CSV row {row_number} changes category for rule_id."
                )
            if term:
                rule_config["terms"].append(term)
            if component:
                rule_config["component_terms"].append(
                    {"component": component, "within_phrase": within_phrase}
                )

    for rule_config in protected_terms.values():
        if not rule_config["component_terms"]:
            del rule_config["component_terms"]

    _build_protected_terms_profile(
        protected_terms,
        include_builtin_protected_clinical_terms=False,
    )
    return protected_terms


def _blank_csv_row(
    row: dict[str, Any],  # Parsed CSV row to test for all-empty fields.
) -> bool:
    """Return true when every parsed CSV field is empty after whitespace trim."""
    return all(not str(value or "").strip() for value in row.values())
