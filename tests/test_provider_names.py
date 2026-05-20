"""Stable provider-name surrogate tests for explicit synthetic aliases."""

import csv

from project_phi import deidentify_csv, deidentify_note
import project_phi.note as note_module
from conftest import _read_csv, _write_csv


def test_residual_provider_single_token_alias_requires_role_context(monkeypatch):
    note = "Radiologist Chen reviewed mammography. Green vegetables were discussed."

    def fake_pydeid(note_text, **_kwargs):
        return [], note_text

    monkeypatch.setattr(note_module, "run_pydeid_deid_string", fake_pydeid)

    result = deidentify_note(
        note,
        stable_provider_name_surrogates=True,
        provider_aliases_by_provider_id={
            "Provider/synth-chen": ["Chen"],
            "Provider/synth-green": ["Green"],
        },
        provider_name_secret="synthetic-provider-secret",
    )

    provider_spans = [
        span
        for span in result.spans
        if span.metadata.get("replacement_source") == "project_residual_provider_alias"
    ]
    assert len(provider_spans) == 1
    assert provider_spans[0].text == "Chen"
    assert "Radiologist Chen" not in result.deidentified_text
    assert "Radiologist " in result.deidentified_text
    assert "Green vegetables" in result.deidentified_text
    assert provider_spans[0].metadata["project_name_policy"] == (
        "residual_explicit_provider_alias"
    )
    assert provider_spans[0].metadata["name_role"] == "known_provider_alias"
    assert provider_spans[0].metadata["alias_match_type"] == "single_token"
    project_start = provider_spans[0].metadata["project_replacement_start"]
    project_end = provider_spans[0].metadata["project_replacement_end"]
    assert result.deidentified_text[project_start:project_end] == provider_spans[0].replacement


def test_residual_provider_full_alias_replaces_without_role_context(monkeypatch):
    note = "Copy to Lena Shore after review."

    def fake_pydeid(note_text, **_kwargs):
        return [], note_text

    monkeypatch.setattr(note_module, "run_pydeid_deid_string", fake_pydeid)

    result = deidentify_note(
        note,
        stable_provider_name_surrogates=True,
        provider_aliases_by_provider_id={"Provider/synth-shore": ["Lena Shore"]},
        provider_name_secret="synthetic-provider-secret",
    )

    provider_spans = [
        span
        for span in result.spans
        if span.metadata.get("replacement_source") == "project_residual_provider_alias"
    ]
    assert len(provider_spans) == 1
    assert provider_spans[0].text == "Lena Shore"
    assert "Lena Shore" not in result.deidentified_text
    assert provider_spans[0].metadata["alias_match_type"] == "full"


def test_csv_provider_aliases_write_sanitized_audit_rows(tmp_path, monkeypatch):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-provider-csv-001",
                "note_id": "Note/synth-provider-csv-001",
                "note_text": "Social worker Green discussed transportation.",
            }
        ],
    )

    def fake_pydeid(note_text, **_kwargs):
        return [], note_text

    monkeypatch.setattr(note_module, "run_pydeid_deid_string", fake_pydeid)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_provider_name_surrogates=True,
        provider_aliases_by_provider_id={"Provider/synth-green": ["Green"]},
        provider_name_secret="synthetic-provider-secret",
    )

    output_rows = _read_csv(output_file)
    audit_rows = _read_csv(audit_file)
    audit_text = audit_file.read_text(encoding="utf-8")
    provider_rows = [
        row
        for row in audit_rows
        if row["replacement_source"] == "project_residual_provider_alias"
    ]
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 1
    assert summary["rows_failed"] == 0
    assert "Social worker Green" not in output_rows[0]["note_text"]
    assert provider_rows
    assert provider_rows[0]["project_name_policy"] == "residual_explicit_provider_alias"
    assert provider_rows[0]["name_role"] == "known_provider_alias"
    assert provider_rows[0]["alias_match_type"] == "single_token"
    assert "Green" not in audit_text
    assert "synthetic-provider-secret" not in audit_text


def test_provider_alias_manifest_loader_and_cli_shape(tmp_path):
    from project_phi.config_loaders import load_provider_alias_manifest

    manifest = tmp_path / "providers.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["provider_id", "alias"])
        writer.writeheader()
        writer.writerow({"provider_id": "Provider/synth-001", "alias": " Chen "})
        writer.writerow({"provider_id": "Provider/synth-001", "alias": "Lena Shore"})

    assert load_provider_alias_manifest(manifest) == {
        "Provider/synth-001": ["Chen", "Lena Shore"]
    }
