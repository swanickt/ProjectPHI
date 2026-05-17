"""Basic public wrapper behavior and pyDeid span-normalization tests.

These tests cover the core single-note API contract:

- `deidentify_note(...)` returns a `DeidentificationResult`;
- normalized spans are returned as `PHISpan` objects;
- original-note offsets line up with `span.text`;
- pyDeid replacement/type metadata is preserved;
- parsed pyDeid date values are normalized into span metadata;
- caller-provided IDs are copied into result/span metadata;
- custom patient name lists are passed through to pyDeid;
- pyDeid NER remains disabled.
"""

import pytest

from project_phi import DeidentificationResult, PHISpan, deidentify_note


def test_wrapper_returns_deidentified_text_and_spans():
    """The public single-note wrapper returns text plus normalized span objects."""
    note = "Test MRN: 011-0111. Follow-up on 2001-12-10. Call 416-555-1212."

    result = deidentify_note(note, include_original_text=True)

    assert isinstance(result, DeidentificationResult)
    assert result.original_text == note
    assert result.deidentified_text != note
    assert result.spans
    assert all(isinstance(span, PHISpan) for span in result.spans)
    assert all(isinstance(span.start, int) and isinstance(span.end, int) for span in result.spans)


def test_span_text_matches_original_offsets_for_string_phi():
    """For string PHI values, each normalized span should match original offsets."""
    note = "Test MRN: 011-0111. Call 416-555-1212."

    result = deidentify_note(note)

    assert result.spans
    for span in result.spans:
        assert note[span.start : span.end] == span.text


def test_pydeid_types_replacement_and_pydeid_surrogate_offsets_are_preserved():
    """Normalization preserves pyDeid types, replacements, and surrogate offsets."""
    note = "Test MRN: 011-0111. Call 416-555-1212."

    result = deidentify_note(note)

    # Do not assert exact randomized pyDeid surrogate values; assert metadata
    # and offset presence instead.
    assert result.warnings == []
    assert all(span.pydeid_types for span in result.spans)
    assert all(span.replacement is not None for span in result.spans)
    assert all("pydeid_surrogate_start" in span.metadata for span in result.spans)
    assert all("pydeid_surrogate_end" in span.metadata for span in result.spans)


def test_date_namedtuple_metadata_is_normalized():
    """pyDeid parsed date objects are converted into plain metadata fields."""
    note = "Follow-up on 2001-12-10."

    result = deidentify_note(note)

    date_spans = [span for span in result.spans if span.label == "DATE"]
    assert date_spans
    parsed = date_spans[0].metadata["parsed_phi"]
    assert parsed["kind"] == "date"
    assert parsed["day"] == "10"
    assert parsed["month"] == "12"
    assert parsed["year"] == "2001"
    assert date_spans[0].text == "2001-12-10"


def test_identifiers_are_attached_to_result_and_span_metadata():
    """Caller-supplied IDs are copied to both result metadata and span metadata."""
    note = "Test MRN: 011-0111."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-001",
        encounter_id="Encounter/synth-001",
        note_id="Note/synth-001",
    )

    assert result.metadata["patient_id"] == "Patient/synth-001"
    assert result.metadata["encounter_id"] == "Encounter/synth-001"
    assert result.metadata["note_id"] == "Note/synth-001"
    assert result.spans
    for span in result.spans:
        assert span.metadata["patient_id"] == "Patient/synth-001"
        assert span.metadata["encounter_id"] == "Encounter/synth-001"
        assert span.metadata["note_id"] == "Note/synth-001"


def test_custom_patient_name_lists_pass_through():
    """Custom patient name lists are forwarded to pyDeid and preserved in types."""
    note = "Patient Zylanda Qorven attended on 10 December 2001."

    result = deidentify_note(
        note,
        custom_patient_first_names={"Zylanda"},
        custom_patient_last_names={"Qorven"},
    )

    detected_text = {span.text for span in result.spans}
    detected_types = " ".join(t for span in result.spans for t in (span.pydeid_types or []))
    assert {"Zylanda", "Qorven"}.issubset(detected_text)
    assert "Custom Patient First Name" in detected_types
    assert "Custom Patient Last Name" in detected_types


def test_ner_is_disabled_by_default_and_rejected_when_requested():
    """The baseline wrapper keeps pyDeid NER off and rejects attempts to enable it."""
    note = "Test MRN: 011-0111."

    result = deidentify_note(note)

    assert result.metadata["named_entity_recognition"] is False
    with pytest.raises(ValueError, match="NER is not enabled"):
        deidentify_note(note, named_entity_recognition=True)