"""Regression tests for overlapping phone/contact pyDeid spans."""

import pytest

from project_phi import PHISpan, deidentify_csv, deidentify_note
import project_phi.reconstruction as reconstruction
from conftest import _read_csv, _write_csv


def _span(
    note: str,
    text: str,
    *,
    label: str,
    replacement: str,
    pydeid_types: list[str],
) -> PHISpan:
    start = note.index(text)
    return PHISpan(
        start=start,
        end=start + len(text),
        text=text,
        label=label,
        source="pyDeid",
        replacement=replacement,
        pydeid_types=pydeid_types,
        metadata={"pydeid_replacement": replacement},
    )


def test_reconstruction_collapses_overlapping_space_separated_phone_spans():
    note = "Call 780-775-8481 226-708-8606."
    spans = [
        _span(
            note,
            "780-775-8481 226",
            label="CONTACT",
            replacement="800-138-7896",
            pydeid_types=["Telephone/Fax", "Telephone/Fax"],
        ),
        _span(
            note,
            "775-8481 226-708-",
            label="ID",
            replacement="6631-715-157",
            pydeid_types=["OHIP", "Telephone/Fax"],
        ),
        _span(
            note,
            "8481 226-708-8606",
            label="ID",
            replacement="250-966-3280",
            pydeid_types=["Telephone/Fax", "OHIP"],
        ),
    ]

    text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert text == "Call <CONTACT>."
    assert len(final_spans) == 1
    assert final_spans[0].start == note.index("780-775-8481")
    assert final_spans[0].end == note.index("8606") + len("8606")
    assert final_spans[0].metadata["replacement_source"] == "project_contact_overlap_repair"
    assert final_spans[0].metadata["project_contact_overlap_policy"] == (
        "collapsed_phone_like_contact_overlap"
    )
    assert "Overlapping phone-like contact spans collapsed during reconstruction." in warnings


def test_deidentify_note_collapses_adjacent_dashed_phone_numbers():
    note = "Call 780-775-8481 226-708-8606."

    result = deidentify_note(note, patient_id="Patient/synth-contact-overlap-001")

    assert result.deidentified_text == "Call <CONTACT>."
    assert "780-775-8481" not in result.deidentified_text
    assert "226-708-8606" not in result.deidentified_text
    assert any(
        span.metadata.get("replacement_source") == "project_contact_overlap_repair"
        for span in result.spans
    )


def test_deidentify_note_collapses_three_adjacent_dashed_phone_numbers():
    note = "Phones: 780-775-8481 226-708-8606 416-555-0101."

    result = deidentify_note(note, patient_id="Patient/synth-contact-overlap-002")

    assert result.deidentified_text == "Phones: <CONTACT>."
    assert "780-775-8481" not in result.deidentified_text
    assert "226-708-8606" not in result.deidentified_text
    assert "416-555-0101" not in result.deidentified_text


def test_deidentify_note_collapses_adjacent_dotted_phone_numbers():
    note = "Phone 780.775.8481 226.708.8606."

    result = deidentify_note(note, patient_id="Patient/synth-contact-overlap-003")

    assert result.deidentified_text == "Phone <CONTACT>."
    assert "780.775.8481" not in result.deidentified_text
    assert "226.708.8606" not in result.deidentified_text


def test_deidentify_csv_audits_contact_overlap_repair_without_raw_phone_text(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    note = "Call 780-775-8481 226-708-8606."
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-contact-overlap-004",
                "note_id": "Note/synth-contact-overlap-004",
                "note_text": note,
            }
        ],
    )

    summary = deidentify_csv(input_file, output_file, audit_output_file=audit_file)

    audit_text = audit_file.read_text(encoding="utf-8")
    audit_rows = _read_csv(audit_file)
    repair_rows = [
        row
        for row in audit_rows
        if row["replacement_source"] == "project_contact_overlap_repair"
    ]
    assert summary["rows_failed"] == 0
    assert repair_rows
    assert repair_rows[0]["project_contact_overlap_policy"] == (
        "collapsed_phone_like_contact_overlap"
    )
    assert repair_rows[0]["project_contact_overlap_span_count"] == "3"
    assert "780-775-8481" not in audit_text
    assert "226-708-8606" not in audit_text


def test_semicolon_separated_phone_numbers_keep_standard_pydeid_spans():
    note = "Call 780-775-8481; 226-708-8606."

    result = deidentify_note(note, patient_id="Patient/synth-contact-overlap-004")

    assert "780-775-8481" not in result.deidentified_text
    assert "226-708-8606" not in result.deidentified_text
    assert not any(
        span.metadata.get("replacement_source") == "project_contact_overlap_repair"
        for span in result.spans
    )


def test_unresolved_mixed_overlap_still_fails_safely():
    note = "Mixed overlap 780-775-8481 ABC."
    spans = [
        _span(
            note,
            "780-775-8481",
            label="CONTACT",
            replacement="800-138-7896",
            pydeid_types=["Telephone/Fax"],
        ),
        PHISpan(
            start=note.index("775"),
            end=note.index("ABC") + len("ABC"),
            text="775-8481 ABC",
            label="NAME",
            source="pyDeid",
            replacement="Morgan",
            pydeid_types=["Last Name (un)"],
            metadata={},
        ),
    ]

    with pytest.raises(ValueError, match="Overlapping pyDeid spans"):
        reconstruction._reconstruct_with_project_replacements(note, spans)
