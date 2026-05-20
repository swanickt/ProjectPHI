"""Stable patient-name surrogate tests for explicit synthetic aliases."""

import pytest

from project_phi import PHISpan, deidentify_note
import project_phi.note as note_module
from conftest import _date_spans, _name_spans, _stable_patient_name_spans
from project_phi.patient_names import (
    _FAKE_FAMILY_NAMES,
    _FAKE_GIVEN_NAMES,
    _build_patient_alias_profile,
    _project_patient_name_replacement,
    _stable_patient_name_identity,
)


def test_stable_patient_name_identity_uses_larger_deterministic_pool_when_available():
    first = _stable_patient_name_identity(
        patient_id="Patient/synth-name-pool-001",
        secret=b"synthetic-secret",
    )
    second = _stable_patient_name_identity(
        patient_id="Patient/synth-name-pool-001",
        secret=b"synthetic-secret",
    )

    assert first == second
    assert first["full"] == f"{first['given']} {first['family']}"
    # When Faker is available through pyDeid, stable names should no longer be
    # constrained to the tiny emergency fallback pools.
    assert first["given"] not in _FAKE_GIVEN_NAMES or first["family"] not in _FAKE_FAMILY_NAMES


def test_stable_patient_name_full_alias_uses_project_replacement_and_offsets():
    note = "Patient Zylanda Qorven attended."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-name-001",
        stable_patient_name_surrogates=True,
        patient_aliases=["Zylanda Qorven"],
        patient_name_secret="synthetic-secret",
    )

    stable_spans = _stable_patient_name_spans(result)
    assert len(stable_spans) == 2
    assert "Zylanda" not in result.deidentified_text
    assert "Qorven" not in result.deidentified_text
    assert f"{stable_spans[0].replacement} {stable_spans[1].replacement}" in result.deidentified_text
    for span in stable_spans:
        assert note[span.start : span.end] == span.text
        project_start = span.metadata["project_replacement_start"]
        project_end = span.metadata["project_replacement_end"]
        assert result.deidentified_text[project_start:project_end] == span.replacement
        assert "pydeid_surrogate_start" in span.metadata
        assert "pydeid_surrogate_end" in span.metadata
        assert span.metadata["project_name_policy"] == "known_patient_alias"
        assert span.metadata["name_role"] == "known_patient_alias"


def test_stable_patient_name_residual_alias_replaces_when_pydeid_emits_no_span(monkeypatch):
    note = "Patient Amelia Rowan attended. Amelia returned."

    def fake_pydeid(note_text, **_kwargs):
        return [], note_text

    monkeypatch.setattr(note_module, "run_pydeid_deid_string", fake_pydeid)

    result = deidentify_note(
        note,
        patient_id="Patient/synth-residual-name-001",
        stable_patient_name_surrogates=True,
        patient_aliases=["Amelia Rowan", "Amelia", "Rowan"],
        patient_name_secret="synthetic-secret",
    )

    residual_spans = [
        span
        for span in result.spans
        if span.metadata.get("replacement_source") == "project_residual_patient_alias"
    ]
    assert len(residual_spans) == 2
    assert "Amelia" not in result.deidentified_text
    assert "Rowan" not in result.deidentified_text
    assert residual_spans[0].metadata["project_name_policy"] == "residual_explicit_patient_alias"
    assert residual_spans[0].metadata["name_role"] == "known_patient_alias"
    assert residual_spans[0].metadata["alias_match_type"] == "full"
    assert residual_spans[1].metadata["alias_match_type"] == "given"
    for span in residual_spans:
        assert note[span.start : span.end] == span.text
        project_start = span.metadata["project_replacement_start"]
        project_end = span.metadata["project_replacement_end"]
        assert result.deidentified_text[project_start:project_end] == span.replacement
    assert result.warnings == []


def test_stable_patient_name_residual_alias_does_not_replace_inside_longer_words(monkeypatch):
    note = "Zylandaville clinic note. Zylanda returned."

    def fake_pydeid(note_text, **_kwargs):
        return [], note_text

    monkeypatch.setattr(note_module, "run_pydeid_deid_string", fake_pydeid)

    result = deidentify_note(
        note,
        patient_id="Patient/synth-residual-name-002",
        stable_patient_name_surrogates=True,
        patient_aliases=["Zylanda"],
        patient_name_secret="synthetic-secret",
    )

    assert "Zylandaville" in result.deidentified_text
    assert "Zylanda returned" not in result.deidentified_text
    residual_spans = [
        span
        for span in result.spans
        if span.metadata.get("replacement_source") == "project_residual_patient_alias"
    ]
    assert len(residual_spans) == 1
    assert residual_spans[0].text == "Zylanda"


def test_stable_patient_name_surrogates_are_deterministic():
    note = "Patient Zylanda Qorven attended."
    kwargs = {
        "patient_id": "Patient/synth-name-002",
        "stable_patient_name_surrogates": True,
        "patient_aliases": ["Zylanda Qorven"],
        "patient_name_secret": "synthetic-secret",
    }

    first = deidentify_note(note, **kwargs)
    second = deidentify_note(note, **kwargs)

    assert first.deidentified_text == second.deidentified_text
    assert [span.replacement for span in _stable_patient_name_spans(first)] == [
        span.replacement for span in _stable_patient_name_spans(second)
    ]

def test_stable_patient_name_full_and_given_aliases_share_fake_component():
    full_note = "Patient Zylanda Qorven attended."
    given_note = "Zylanda returned for review."
    kwargs = {
        "patient_id": "Patient/synth-name-003",
        "stable_patient_name_surrogates": True,
        "patient_aliases": ["Zylanda Qorven"],
        "patient_name_secret": "synthetic-secret",
    }

    full_result = deidentify_note(full_note, **kwargs)
    given_result = deidentify_note(given_note, **kwargs)

    full_given_span = [span for span in _stable_patient_name_spans(full_result) if span.text == "Zylanda"][0]
    given_span = _stable_patient_name_spans(given_result)[0]
    assert given_span.text == "Zylanda"
    assert given_span.replacement == full_given_span.replacement
    assert given_span.metadata["alias_match_type"] == "given"

def test_stable_patient_name_standalone_given_alias_uses_fake_given_only():
    note = "Zylanda returned for review."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-name-003a",
        stable_patient_name_surrogates=True,
        patient_aliases=["Zylanda"],
        patient_name_secret="synthetic-secret",
    )

    stable_spans = _stable_patient_name_spans(result)
    assert len(stable_spans) == 1
    assert stable_spans[0].text == "Zylanda"
    assert stable_spans[0].metadata["alias_match_type"] == "given"
    assert " " not in stable_spans[0].replacement
    assert result.deidentified_text == f"{stable_spans[0].replacement} returned for review."

def test_stable_patient_name_family_alias_requires_explicit_alias():
    note = "Qorven returned for review."

    without_family_alias = deidentify_note(
        note,
        patient_id="Patient/synth-name-004",
        stable_patient_name_surrogates=True,
        patient_aliases=["Zylanda Qorven"],
        patient_name_secret="synthetic-secret",
    )
    with_family_alias = deidentify_note(
        note,
        patient_id="Patient/synth-name-004",
        stable_patient_name_surrogates=True,
        patient_aliases=["Zylanda Qorven", "Qorven"],
        patient_name_secret="synthetic-secret",
    )

    assert _stable_patient_name_spans(without_family_alias) == []
    stable_spans = _stable_patient_name_spans(with_family_alias)
    assert len(stable_spans) == 1
    assert stable_spans[0].text == "Qorven"
    assert stable_spans[0].metadata["alias_match_type"] == "family"

def test_stable_patient_name_family_alias_with_full_name_context_uses_fake_family():
    note = "Qorven returned for review."
    full_name_result = deidentify_note(
        "Patient Zylanda Qorven attended.",
        patient_id="Patient/synth-name-004a",
        stable_patient_name_surrogates=True,
        patient_aliases=["Zylanda Qorven", "Qorven"],
        patient_name_secret="synthetic-secret",
    )

    result = deidentify_note(
        note,
        patient_id="Patient/synth-name-004a",
        stable_patient_name_surrogates=True,
        patient_aliases=["Zylanda Qorven", "Qorven"],
        patient_name_secret="synthetic-secret",
    )

    full_family_span = [span for span in _stable_patient_name_spans(full_name_result) if span.text == "Qorven"][0]
    stable_span = _stable_patient_name_spans(result)[0]
    assert stable_span.replacement == full_family_span.replacement
    assert stable_span.metadata["alias_match_type"] == "family"

def test_stable_patient_name_title_family_alias_preserves_title():
    note = "Mr. Qorven attended."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-name-005",
        stable_patient_name_surrogates=True,
        patient_aliases=["Mr. Qorven"],
        patient_name_secret="synthetic-secret",
    )

    stable_spans = _stable_patient_name_spans(result)
    assert stable_spans
    assert result.deidentified_text.startswith("Mr. ")
    assert "Qorven" not in result.deidentified_text
    assert stable_spans[0].replacement in result.deidentified_text


def test_stable_patient_name_french_title_family_alias_preserves_title():
    note = "Mme Qorven attended."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-name-005-fr",
        stable_patient_name_surrogates=True,
        patient_aliases=["Mme Qorven"],
        patient_name_secret="synthetic-secret",
    )

    stable_spans = _stable_patient_name_spans(result)
    assert stable_spans
    assert result.deidentified_text.startswith("Mme ")
    assert "Qorven" not in result.deidentified_text
    assert stable_spans[0].metadata["alias_match_type"] == "family"


def test_stable_patient_name_french_title_family_alias_profile_is_supported():
    profile = _build_patient_alias_profile(["Mme Qorven"])
    span = PHISpan(
        start=0,
        end=len("Mme Qorven"),
        text="Mme Qorven",
        label="NAME",
        source="synthetic",
    )

    replacement = _project_patient_name_replacement(
        span,
        original_text="Mme Qorven attended.",
        alias_profile=profile,
        identity={"given": "Alex", "family": "Fraser", "full": "Alex Fraser"},
    )

    assert replacement == ("Mme Fraser", "title_family")

def test_stable_patient_name_ambiguous_single_token_alias_raises():
    note = "Jordan attended."

    with pytest.raises(ValueError, match="ambiguous single-token"):
        deidentify_note(
            note,
            patient_id="Patient/synth-name-005a",
            stable_patient_name_surrogates=True,
            patient_aliases=["Jordan Smith", "Alex Jordan", "Jordan"],
            patient_name_secret="synthetic-secret",
        )

def test_stable_patient_name_unknown_name_uses_pydeid_replacement():
    note = "Patient Zylanda Qorven met Xavion Norel."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-name-006",
        stable_patient_name_surrogates=True,
        patient_aliases=["Zylanda Qorven"],
        patient_name_secret="synthetic-secret",
        custom_dr_first_names={"Xavion"},
        custom_dr_last_names={"Norel"},
    )

    unknown_spans = [span for span in _name_spans(result) if span.text in {"Xavion", "Norel"}]
    assert unknown_spans
    # Unknown names may be clinicians or family members, so they must not be
    # forced into the stable patient identity.
    for span in unknown_spans:
        assert span.metadata["replacement_source"] == "pyDeid"
        assert span.metadata["project_name_policy"] == "unknown_name_pydeid"
        assert span.metadata["name_role"] == "unknown_name"
        assert span.metadata["alias_match_type"] == ""
        assert span.replacement == span.metadata["pydeid_replacement"]

def test_stable_patient_name_requires_patient_id_secret_aliases_and_name_detection():
    note = "Patient Zylanda Qorven attended."

    with pytest.raises(ValueError, match="patient_id"):
        deidentify_note(
            note,
            stable_patient_name_surrogates=True,
            patient_aliases=["Zylanda Qorven"],
            patient_name_secret="synthetic-secret",
        )
    with pytest.raises(ValueError, match="patient_name_secret"):
        deidentify_note(
            note,
            patient_id="Patient/synth-name-007",
            stable_patient_name_surrogates=True,
            patient_aliases=["Zylanda Qorven"],
        )
    with pytest.raises(ValueError, match="patient alias"):
        deidentify_note(
            note,
            patient_id="Patient/synth-name-007",
            stable_patient_name_surrogates=True,
            patient_aliases=[],
            patient_name_secret="synthetic-secret",
        )
    with pytest.raises(ValueError, match="name detection"):
        deidentify_note(
            note,
            patient_id="Patient/synth-name-007",
            stable_patient_name_surrogates=True,
            patient_aliases=["Zylanda Qorven"],
            patient_name_secret="synthetic-secret",
            types=["dates"],
        )

def test_stable_patient_name_secret_env_var_success(monkeypatch):
    note = "Patient Zylanda Qorven attended."
    monkeypatch.setenv("PROJECT_PHI_TEST_NAME_SECRET", "synthetic-secret")

    result = deidentify_note(
        note,
        patient_id="Patient/synth-name-008",
        stable_patient_name_surrogates=True,
        patient_aliases=["Zylanda Qorven"],
        patient_name_secret_env_var="PROJECT_PHI_TEST_NAME_SECRET",
    )

    assert _stable_patient_name_spans(result)
    assert "Zylanda" not in result.deidentified_text
    assert "Qorven" not in result.deidentified_text

def test_stable_patient_name_secret_env_var_missing_or_empty_raises(monkeypatch):
    note = "Patient Zylanda Qorven attended."
    monkeypatch.delenv("PROJECT_PHI_MISSING_NAME_SECRET", raising=False)

    with pytest.raises(ValueError, match="patient_name_secret"):
        deidentify_note(
            note,
            patient_id="Patient/synth-name-009",
            stable_patient_name_surrogates=True,
            patient_aliases=["Zylanda Qorven"],
            patient_name_secret_env_var="PROJECT_PHI_MISSING_NAME_SECRET",
        )

    monkeypatch.setenv("PROJECT_PHI_EMPTY_NAME_SECRET", "")
    with pytest.raises(ValueError, match="patient_name_secret"):
        deidentify_note(
            note,
            patient_id="Patient/synth-name-009",
            stable_patient_name_surrogates=True,
            patient_aliases=["Zylanda Qorven"],
            patient_name_secret_env_var="PROJECT_PHI_EMPTY_NAME_SECRET",
        )

def test_stable_date_shift_and_patient_names_share_project_reconstruction():
    note = "Patient Zylanda Qorven had follow-up on 2001-12-10."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-name-date-001",
        stable_date_shift=True,
        date_shift_secret="synthetic-date-secret",
        stable_patient_name_surrogates=True,
        patient_aliases=["Zylanda Qorven"],
        patient_name_secret="synthetic-name-secret",
    )

    project_spans = [
        span
        for span in result.spans
        if span.metadata.get("replacement_source")
        in {"project_stable_date_shift", "project_stable_patient_name"}
    ]
    assert any(span.label == "DATE" for span in project_spans)
    assert any(span.label == "NAME" for span in project_spans)
    assert "2001-12-10" not in result.deidentified_text
    assert "Zylanda" not in result.deidentified_text
    assert "Qorven" not in result.deidentified_text
    for span in project_spans:
        assert note[span.start : span.end] == span.text
        project_start = span.metadata["project_replacement_start"]
        project_end = span.metadata["project_replacement_end"]
        assert result.deidentified_text[project_start:project_end] == span.replacement
    warning_text = " ".join(result.warnings)
    assert "2001-12-10" not in warning_text
    assert "Zylanda" not in warning_text
    assert "Qorven" not in warning_text
