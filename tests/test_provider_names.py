"""Stable provider-name surrogate tests for explicit synthetic aliases."""

import csv

from project_phi import PHISpan, deidentify_csv, deidentify_note
import project_phi.note as note_module
import project_phi.reconstruction as reconstruction
from project_phi.provider_names import (
    _build_provider_alias_profile,
    _stable_provider_name_identities,
)
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


def _provider_profile_and_identities(aliases_by_provider_id):
    profile = _build_provider_alias_profile(aliases_by_provider_id)
    identities = _stable_provider_name_identities(
        profile,
        secret=b"synthetic-provider-secret",
    )
    return profile, identities


def _name_span(note, text, replacement="Donald Dunn"):
    start = note.index(text)
    return PHISpan(
        start=start,
        end=start + len(text),
        text=text,
        label="NAME",
        source="pyDeid",
        replacement=replacement,
        pydeid_types=["Custom Doctor Last Name"],
        metadata={
            "pydeid_replacement": replacement,
            "pydeid_surrogate_start": 0,
            "pydeid_surrogate_end": len(replacement),
        },
    )


def test_provider_alias_span_preserves_trailing_lowercase_action_word():
    note = "Nurse Taylor reviewed wound care."
    profile, identities = _provider_profile_and_identities(
        {"Provider/synth-taylor": ["Taylor"]}
    )
    span = _name_span(note, "Taylor reviewed")

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        provider_name_alias_profile=profile,
        provider_name_identities=identities,
    )

    assert "Taylor" not in text
    assert "reviewed wound care" in text
    assert text.startswith("Nurse ")
    assert spans[0].metadata["replacement_source"] == "project_stable_provider_name"
    assert spans[0].metadata["project_name_policy"] == "known_provider_alias"
    assert spans[0].metadata["name_role"] == "known_provider_alias"
    assert spans[0].metadata["alias_match_type"] == "single_token_trailing_action"
    start = spans[0].metadata["project_replacement_start"]
    end = spans[0].metadata["project_replacement_end"]
    assert text[start:end] == spans[0].replacement


def test_provider_full_alias_span_preserves_trailing_lowercase_action_word():
    note = "Dr. Lena Shore reviewed mammography."
    profile, identities = _provider_profile_and_identities(
        {"Provider/synth-shore": ["Lena Shore"]}
    )
    span = _name_span(note, "Lena Shore reviewed")

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        provider_name_alias_profile=profile,
        provider_name_identities=identities,
    )

    assert "Lena Shore" not in text
    assert "reviewed mammography" in text
    assert spans[0].metadata["alias_match_type"] == "full_trailing_action"


def test_provider_trailing_action_rescue_does_not_preserve_capitalized_surname():
    note = "Nurse Taylor Cook reviewed wound care."
    profile, identities = _provider_profile_and_identities(
        {"Provider/synth-taylor": ["Taylor"], "Provider/synth-cook": ["Cook"]}
    )
    span = _name_span(note, "Taylor Cook")

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        provider_name_alias_profile=profile,
        provider_name_identities=identities,
    )

    assert "Taylor Cook" not in text
    assert "Cook reviewed" not in text
    assert "reviewed wound care" in text
    assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_provider_trailing_action_rescue_requires_following_context():
    note = "Nurse Taylor reviewed."
    profile, identities = _provider_profile_and_identities(
        {"Provider/synth-taylor": ["Taylor"]}
    )
    span = _name_span(note, "Taylor reviewed")

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        provider_name_alias_profile=profile,
        provider_name_identities=identities,
    )

    assert text == "Nurse Donald Dunn."
    assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_provider_split_full_alias_components_use_same_stable_identity():
    note = "Dr. Lena Shore reviewed mammography."
    profile, identities = _provider_profile_and_identities(
        {"Provider/synth-shore": ["Lena Shore", "Shore"]}
    )
    spans = [
        _name_span(note, "Lena", replacement="Kimberly"),
        _name_span(note, "Shore", replacement="Ford"),
    ]

    text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
        provider_name_alias_profile=profile,
        provider_name_identities=identities,
    )

    identity = identities["Provider/synth-shore"]
    assert text == f"Dr. {identity['full']} reviewed mammography."
    assert final_spans[0].metadata["replacement_source"] == "project_stable_provider_name"
    assert final_spans[0].metadata["alias_match_type"] == "given"
    assert final_spans[1].metadata["replacement_source"] == "project_stable_provider_name"
    assert final_spans[1].metadata["alias_match_type"] == "family"


def test_duplicate_provider_alias_uses_shared_ambiguous_surrogate():
    note = "Radiologist Chen reviewed mammography."
    profile, identities = _provider_profile_and_identities(
        {
            "Provider/synth-chen-1": ["Adam Chen", "Chen"],
            "Provider/synth-chen-2": ["Emily Chen", "Chen"],
        }
    )
    span = _name_span(note, "Chen", replacement="Donald")

    text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        provider_name_alias_profile=profile,
        provider_name_identities=identities,
    )

    assert "Chen" not in text
    assert text.startswith("Radiologist ")
    assert final_spans[0].metadata["replacement_source"] == "project_stable_provider_name"
    assert final_spans[0].metadata["project_name_policy"] == "ambiguous_provider_alias"
    assert final_spans[0].metadata["name_role"] == "known_provider_alias"
    assert final_spans[0].metadata["alias_match_type"] == "ambiguous_single_token"


def test_duplicate_provider_alias_is_stable_across_notes():
    profile, identities = _provider_profile_and_identities(
        {
            "Provider/synth-chen-1": ["Adam Chen", "Chen"],
            "Provider/synth-chen-2": ["Emily Chen", "Chen"],
        }
    )
    outputs = []
    replacements = []

    for note in [
        "Radiologist Chen reviewed mammography.",
        "Dr. Chen signed the report.",
    ]:
        span = _name_span(note, "Chen", replacement="Donald")
        text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
            note,
            [span],
            provider_name_alias_profile=profile,
            provider_name_identities=identities,
        )
        outputs.append(text)
        replacements.append(final_spans[0].replacement)

    assert replacements[0] == replacements[1]
    assert "Chen" not in outputs[0]
    assert "Chen" not in outputs[1]


def test_duplicate_provider_single_token_alias_still_requires_role_context():
    note = "Chen vegetables were discussed."
    profile, identities = _provider_profile_and_identities(
        {
            "Provider/synth-chen-1": ["Adam Chen", "Chen"],
            "Provider/synth-chen-2": ["Emily Chen", "Chen"],
        }
    )
    span = _name_span(note, "Chen", replacement="Donald")

    text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        provider_name_alias_profile=profile,
        provider_name_identities=identities,
    )

    assert text == "Donald vegetables were discussed."
    assert final_spans[0].metadata["replacement_source"] == "pyDeid"


def test_duplicate_provider_alias_does_not_override_specific_full_alias():
    note = "Dr. Adam Chen reviewed mammography."
    profile, identities = _provider_profile_and_identities(
        {
            "Provider/synth-chen-1": ["Adam Chen", "Chen"],
            "Provider/synth-chen-2": ["Emily Chen", "Chen"],
        }
    )
    span = _name_span(note, "Adam Chen", replacement="Donald Dunn")

    text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        provider_name_alias_profile=profile,
        provider_name_identities=identities,
    )

    assert text == f"Dr. {identities['Provider/synth-chen-1']['full']} reviewed mammography."
    assert final_spans[0].metadata["replacement_source"] == "project_stable_provider_name"
    assert final_spans[0].metadata["project_name_policy"] == "known_provider_alias"
    assert final_spans[0].metadata["alias_match_type"] == "full"


def test_duplicate_provider_alias_residual_csv_does_not_fail_rows(tmp_path, monkeypatch):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-provider-csv-duplicate-001",
                "note_id": "Note/synth-provider-csv-duplicate-001",
                "note_text": "Radiologist Chen reviewed mammography.",
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
        provider_aliases_by_provider_id={
            "Provider/synth-chen-1": ["Adam Chen", "Chen"],
            "Provider/synth-chen-2": ["Emily Chen", "Chen"],
        },
        provider_name_secret="synthetic-provider-secret",
    )

    output_rows = _read_csv(output_file)
    audit_rows = _read_csv(audit_file)
    provider_rows = [
        row
        for row in audit_rows
        if row["replacement_source"] == "project_residual_provider_alias"
    ]
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 1
    assert summary["rows_failed"] == 0
    assert "Chen" not in output_rows[0]["note_text"]
    assert provider_rows
    assert provider_rows[0]["project_name_policy"] == "ambiguous_provider_alias"
    assert provider_rows[0]["alias_match_type"] == "ambiguous_single_token"


def test_provider_split_full_alias_is_consistent_across_notes():
    profile, identities = _provider_profile_and_identities(
        {"Provider/synth-mason": ["Theo Mason", "Mason"]}
    )
    outputs = []
    for note in ["Copy to Dr. Theo Mason.", "Follow-up with Dr. Theo Mason."]:
        spans = [
            _name_span(note, "Theo", replacement="Maria"),
            _name_span(note, "Mason", replacement="Jason"),
        ]
        text, _final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
            note,
            spans,
            provider_name_alias_profile=profile,
            provider_name_identities=identities,
        )
        outputs.append(text)

    identity = identities["Provider/synth-mason"]
    assert outputs == [
        f"Copy to Dr. {identity['full']}.",
        f"Follow-up with Dr. {identity['full']}.",
    ]


def test_provider_family_component_from_full_alias_does_not_match_standalone_without_role():
    note = "Mason reviewed mammography."
    profile, identities = _provider_profile_and_identities(
        {"Provider/synth-mason": ["Theo Mason", "Mason"]}
    )
    span = _name_span(note, "Mason", replacement="Jason")

    text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        provider_name_alias_profile=profile,
        provider_name_identities=identities,
    )

    assert text == "Jason reviewed mammography."
    assert final_spans[0].metadata["replacement_source"] == "pyDeid"


def test_provider_adjacent_action_span_preserves_lowercase_action_word():
    note = "Nurse Taylor reviewed wound care."
    profile, identities = _provider_profile_and_identities(
        {"Provider/synth-taylor": ["Taylor"]}
    )
    spans = [
        _name_span(note, "Taylor", replacement="Alicia"),
        _name_span(note, "reviewed", replacement="Clarke"),
    ]

    text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
        provider_name_alias_profile=profile,
        provider_name_identities=identities,
    )

    assert "Taylor" not in text
    assert "Clarke wound care" not in text
    assert "reviewed wound care" in text
    assert final_spans[0].metadata["replacement_source"] == "project_stable_provider_name"
    assert final_spans[1].metadata["replacement_source"] == (
        "project_provider_adjacent_action_word_veto"
    )
    assert final_spans[1].metadata["project_name_policy"] == (
        "provider_alias_adjacent_action_word_veto"
    )
    assert final_spans[1].metadata["name_role"] == "not_name_action_word"
    assert final_spans[1].metadata["project_provider_action_word"] == "reviewed"
    start = final_spans[1].metadata["project_replacement_start"]
    end = final_spans[1].metadata["project_replacement_end"]
    assert text[start:end] == "reviewed"


def test_provider_adjacent_action_span_handles_assessed_symptoms():
    note = "Nurse Patel assessed symptoms."
    profile, identities = _provider_profile_and_identities(
        {"Provider/synth-patel": ["Patel"]}
    )
    spans = [
        _name_span(note, "Patel", replacement="Fitzgerald"),
        _name_span(note, "assessed", replacement="Johns"),
    ]

    text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
        provider_name_alias_profile=profile,
        provider_name_identities=identities,
    )

    assert "Patel" not in text
    assert "Johns symptoms" not in text
    assert "assessed symptoms" in text
    assert final_spans[1].metadata["replacement_source"] == (
        "project_provider_adjacent_action_word_veto"
    )


def test_provider_adjacent_action_span_requires_provider_alias_before_action():
    note = "Nurse Taylor reviewed wound care."
    profile, identities = _provider_profile_and_identities(
        {"Provider/synth-other": ["Morgan"]}
    )
    spans = [
        _name_span(note, "Taylor", replacement="Alicia"),
        _name_span(note, "reviewed", replacement="Clarke"),
    ]

    text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
        provider_name_alias_profile=profile,
        provider_name_identities=identities,
    )

    assert text == "Nurse Alicia Clarke wound care."
    assert final_spans[1].metadata["replacement_source"] == "pyDeid"


def test_provider_adjacent_action_span_does_not_preserve_without_following_context():
    note = "Nurse Taylor reviewed."
    profile, identities = _provider_profile_and_identities(
        {"Provider/synth-taylor": ["Taylor"]}
    )
    spans = [
        _name_span(note, "Taylor", replacement="Alicia"),
        _name_span(note, "reviewed", replacement="Clarke"),
    ]

    text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
        provider_name_alias_profile=profile,
        provider_name_identities=identities,
    )

    assert "Taylor" not in text
    assert text.endswith("Clarke.")
    assert final_spans[1].metadata["replacement_source"] == "pyDeid"


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
