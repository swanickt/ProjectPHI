"""Config loader tests using synthetic manifests and regex rules only."""

import json

import pytest

from project_phi.config_loaders import (
    load_custom_regexes_json,
    load_patient_alias_manifest,
    load_protected_clinical_terms_csv,
    load_provider_alias_manifest,
)


def test_load_patient_alias_manifest_valid_synthetic_csv(tmp_path):
    manifest = tmp_path / "aliases.csv"
    manifest.write_text(
        "patient_id,alias\n"
        " Patient/synth-001 , Zylanda Qorven \n"
        "Patient/synth-001,Zylanda\n"
        "\n"
        "Patient/synth-002,Marlo Venn\n",
        encoding="utf-8",
    )

    assert load_patient_alias_manifest(manifest) == {
        "Patient/synth-001": ["Zylanda Qorven", "Zylanda"],
        "Patient/synth-002": ["Marlo Venn"],
    }


def test_load_patient_alias_manifest_rejects_missing_columns(tmp_path):
    manifest = tmp_path / "aliases.csv"
    manifest.write_text("patient_id,name\nPatient/synth-001,Zylanda Qorven\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required columns") as exc_info:
        load_patient_alias_manifest(manifest)

    assert "Zylanda" not in str(exc_info.value)


@pytest.mark.parametrize(
    "contents",
    [
        "patient_id,alias\n, Zylanda Qorven\n",
        "patient_id,alias\nPatient/synth-001, \n",
    ],
)
def test_load_patient_alias_manifest_rejects_empty_values_with_row_number(tmp_path, contents):
    manifest = tmp_path / "aliases.csv"
    manifest.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match="row 2") as exc_info:
        load_patient_alias_manifest(manifest)

    assert "Zylanda" not in str(exc_info.value)
    assert "Patient/synth-001" not in str(exc_info.value)


def test_load_provider_alias_manifest_valid_synthetic_csv(tmp_path):
    manifest = tmp_path / "providers.csv"
    manifest.write_text(
        "provider_id,alias\n"
        " Provider/synth-001 , Chen \n"
        "Provider/synth-001,Lena Shore\n"
        "\n"
        "Provider/synth-002,Green\n",
        encoding="utf-8",
    )

    assert load_provider_alias_manifest(manifest) == {
        "Provider/synth-001": ["Chen", "Lena Shore"],
        "Provider/synth-002": ["Green"],
    }


def test_load_provider_alias_manifest_rejects_missing_columns(tmp_path):
    manifest = tmp_path / "providers.csv"
    manifest.write_text("provider_id,name\nProvider/synth-001,Chen\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required columns") as exc_info:
        load_provider_alias_manifest(manifest)

    assert "Chen" not in str(exc_info.value)


@pytest.mark.parametrize(
    "contents",
    [
        "provider_id,alias\n, Chen\n",
        "provider_id,alias\nProvider/synth-001, \n",
    ],
)
def test_load_provider_alias_manifest_rejects_empty_values_with_row_number(tmp_path, contents):
    manifest = tmp_path / "providers.csv"
    manifest.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match="row 2") as exc_info:
        load_provider_alias_manifest(manifest)

    assert "Chen" not in str(exc_info.value)
    assert "Provider/synth-001" not in str(exc_info.value)


def test_load_custom_regexes_json_valid_synthetic_config(tmp_path):
    config = tmp_path / "custom_regexes.json"
    payload = {
        "synthetic_accession": {
            "phi_type": "Synthetic Accession",
            "pattern": r"\bSYN-ACC-\d{4}\b",
            "replacement": "<SYNTHETIC_ACCESSION>",
        }
    }
    config.write_text(json.dumps(payload), encoding="utf-8")

    assert load_custom_regexes_json(config) == payload


def test_load_custom_regexes_json_rejects_invalid_json(tmp_path):
    config = tmp_path / "custom_regexes.json"
    config.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid"):
        load_custom_regexes_json(config)


@pytest.mark.parametrize(
    "payload, message",
    [
        ([], "top-level object"),
        ({"": {"phi_type": "Synthetic Accession", "pattern": r"\bSYN-ACC-\d{4}\b"}}, "rule ID"),
        ({"synthetic_accession": {"pattern": r"\bSYN-ACC-\d{4}\b"}}, "phi_type"),
        ({"synthetic_accession": {"phi_type": "Synthetic Accession"}}, "pattern"),
        (
            {
                "synthetic_accession": {
                    "phi_type": "Synthetic Accession",
                    "pattern": r"\bSYN-ACC-\d{4}\b",
                    "replacement": 123,
                }
            },
            "replacement",
        ),
    ],
)
def test_load_custom_regexes_json_rejects_invalid_shape_without_raw_patterns(
    tmp_path,
    payload,
    message,
):
    config = tmp_path / "custom_regexes.json"
    config.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message) as exc_info:
        load_custom_regexes_json(config)

    assert r"\bSYN-ACC-" not in str(exc_info.value)


def test_load_protected_clinical_terms_csv_valid_synthetic_config(tmp_path):
    config = tmp_path / "protected_terms.csv"
    config.write_text(
        "rule_id,category,term\n"
        "synthetic_breast,breast_imaging, tomosynthesis \n"
        "synthetic_breast,breast_imaging,mammography with tomosynthesis\n"
        "\n"
        "synthetic_status,disease_status,remission\n",
        encoding="utf-8",
    )

    assert load_protected_clinical_terms_csv(config) == {
        "synthetic_breast": {
            "category": "breast_imaging",
            "terms": ["tomosynthesis", "mammography with tomosynthesis"],
        },
        "synthetic_status": {
            "category": "disease_status",
            "terms": ["remission"],
        },
    }


def test_load_protected_clinical_terms_csv_accepts_component_phrase_rows(tmp_path):
    config = tmp_path / "protected_terms.csv"
    config.write_text(
        "rule_id,category,term,component,within_phrase\n"
        "synthetic_tools,clinical_tools,,Chelsea,Chelsea Critical Care Physical Assessment Tool\n"
        "synthetic_tools,clinical_tools,JOA score,,\n",
        encoding="utf-8",
    )

    assert load_protected_clinical_terms_csv(config) == {
        "synthetic_tools": {
            "category": "clinical_tools",
            "terms": ["JOA score"],
            "component_terms": [
                {
                    "component": "Chelsea",
                    "within_phrase": "Chelsea Critical Care Physical Assessment Tool",
                }
            ],
        },
    }


def test_load_protected_clinical_terms_csv_rejects_missing_columns(tmp_path):
    config = tmp_path / "protected_terms.csv"
    config.write_text("rule_id,term\nsynthetic_breast,tomosynthesis\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required columns") as exc_info:
        load_protected_clinical_terms_csv(config)

    assert "tomosynthesis" not in str(exc_info.value)


@pytest.mark.parametrize(
    "contents, message",
    [
        ("rule_id,category,term\n,breast_imaging,tomosynthesis\n", "row 2"),
        ("rule_id,category,term\nsynthetic_breast,,tomosynthesis\n", "row 2"),
        ("rule_id,category,term\nsynthetic_breast,breast_imaging,\n", "row 2"),
    ],
)
def test_load_protected_clinical_terms_csv_rejects_empty_values_safely(
    tmp_path,
    contents,
    message,
):
    config = tmp_path / "protected_terms.csv"
    config.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message) as exc_info:
        load_protected_clinical_terms_csv(config)

    assert "tomosynthesis" not in str(exc_info.value)


def test_load_protected_clinical_terms_csv_rejects_incomplete_component_rows_safely(
    tmp_path,
):
    config = tmp_path / "protected_terms.csv"
    config.write_text(
        "rule_id,category,term,component,within_phrase\n"
        "synthetic_tools,clinical_tools,,Chelsea,\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="row 2") as exc_info:
        load_protected_clinical_terms_csv(config)

    assert "Chelsea" not in str(exc_info.value)
