"""Stable patient-name surrogate tests for explicit synthetic aliases.

These tests cover ProjectPHI's stable patient-name policy.

Main contracts covered:
- stable fake identities are deterministic for the same patient/secret pair;
- explicit patient aliases can receive project-stable replacements;
- given-name, family-name, full-name, and title-family aliases map to the right
  fake-name components;
- standalone family-name replacement is conservative and requires explicit
  alias support;
- ambiguous single-token aliases fail closed;
- unknown names remain pyDeid replacements instead of being treated as patient
  aliases;
- stable patient-name surrogates require patient ID, secret, aliases, and name
  detection;
- environment-variable secrets work without storing or printing the secret;
- stable patient-name and stable date-shift policies share project reconstruction
  while keeping offsets separate.

All names, identifiers, and notes in this file are synthetic.
"""

import pytest

from project_phi import PHISpan, deidentify_note
from conftest import _date_spans, _name_spans, _stable_patient_name_spans
from project_phi.patient_names import (
    _FAKE_FAMILY_NAMES,
    _FAKE_GIVEN_NAMES,
    _build_patient_alias_profile,
    _project_patient_name_replacement,
    _stable_patient_name_identity,
)


# Deterministic fake identity generation.


def test_stable_patient_name_identity_uses_larger_deterministic_pool_when_available():
    """Stable identity generation is deterministic and prefers Faker over fallback pools."""
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


# Explicit alias replacement behavior.


def test_stable_patient_name_full_alias_uses_project_replacement_and_offsets():
    """Full patient aliases use project replacements with original/final offsets separated."""
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


def test_stable_patient_name_surrogates_are_deterministic():
    """The same patient, secret, aliases, and note produce the same replacements."""
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
    """Full-name and given-name aliases share the same fake given-name component."""
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
    """A standalone given-name alias is replaced with only the fake given name."""
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
    """A standalone family-name span is replaced only when explicitly configured."""
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
    """Explicit family aliases reuse the fake family name from the full-name identity."""
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
    """English title-family aliases preserve the title and replace the family name."""
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
    """French title-family aliases preserve the title and replace the family name."""
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
    """The alias profile supports French title-family replacement directly."""
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


# Conservative fallback and validation behavior.


def test_stable_patient_name_ambiguous_single_token_alias_raises():
    """Ambiguous single-token aliases fail closed instead of guessing name role."""
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
    """Unknown detected names stay pyDeid-only and are not forced into patient identity."""
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
    """Stable patient-name mode requires ID, secret, aliases, and pyDeid name detection."""
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
    """Patient-name secret can be supplied through an environment variable."""
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
    """Missing or empty patient-name secret environment variables fail closed."""
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


# Shared reconstruction with date shifting.


def test_stable_date_shift_and_patient_names_share_project_reconstruction():
    """Date shifting and patient-name replacement share reconstruction safely."""
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