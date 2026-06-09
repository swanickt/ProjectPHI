"""Semantic-preservation tests for dotted decimal-like contact false positives."""

import csv

from project_phi import PHISpan, deidentify_csv, deidentify_note
import project_phi.reconstruction as reconstruction
from conftest import _read_csv, _write_csv


def _contact_span(text, note):
    return PHISpan(
        start=note.index(text),
        end=note.index(text) + len(text),
        text=text,
        label="CONTACT",
        source="pyDeid",
        replacement="416-555-1212",
        pydeid_types=["Telephone/Fax"],
        metadata={"pydeid_replacement": "416-555-1212"},
    )


def test_reconstruction_preserves_standalone_decimal_code_fragment():
    note = "Value was 189.1000043."
    spans = [_contact_span("189.1000043", note)]

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert deidentified_text == note
    assert warnings == []
    assert final_spans[0].action == "preserved"
    assert final_spans[0].metadata["replacement_source"] == "project_decimal_code_veto"
    assert (
        final_spans[0].metadata["project_decimal_code_policy"]
        == "preserved_decimal_like_code_fragment"
    )
    assert final_spans[0].metadata["project_decimal_code_context"] == "non_phone_dotted_grouping"


def test_reconstruction_preserves_decimal_code_with_colon_continuation():
    note = "Value was (189.100.0043:4.002.001)."
    spans = [_contact_span("(189.100.0043", note)]

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert deidentified_text == note
    assert warnings == []
    assert final_spans[0].metadata["project_decimal_code_context"] == (
        "colon_dotted_numeric_continuation"
    )


def test_reconstruction_still_replaces_dotted_phone_numbers():
    note = "Call 416.555.1212 tomorrow."
    spans = [_contact_span("416.555.1212", note)]

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert deidentified_text == "Call 416-555-1212 tomorrow."
    assert warnings == []
    assert final_spans[0].action == "replaced"
    assert final_spans[0].metadata["replacement_source"] == "pyDeid"
    assert "project_decimal_code_policy" not in final_spans[0].metadata


def test_reconstruction_preserves_long_float_measurement_fragment():
    note = "Tumour Size (cm). 6.2000000000000002. Histology showed carcinoma."
    spans = [_contact_span("2000000000000002", note)]

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert deidentified_text == note
    assert warnings == []
    assert final_spans[0].metadata["replacement_source"] == "project_decimal_code_veto"
    assert final_spans[0].metadata["project_decimal_code_context"] == (
        "long_float_measurement_context"
    )


def test_reconstruction_does_not_preserve_long_digit_contact_without_measurement_context():
    note = "Call 2000000000000002 tomorrow."
    spans = [_contact_span("2000000000000002", note)]

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert deidentified_text == "Call 416-555-1212 tomorrow."
    assert warnings == []
    assert final_spans[0].metadata["replacement_source"] == "pyDeid"
    assert "project_decimal_code_policy" not in final_spans[0].metadata


def test_reconstruction_does_not_preserve_long_float_fragment_from_embedded_mm_substring():
    note = "Immunohistochemical testing listed artifact 6.2000000000000002."
    spans = [_contact_span("2000000000000002", note)]

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert deidentified_text == (
        "Immunohistochemical testing listed artifact 6.416-555-1212."
    )
    assert warnings == []
    assert final_spans[0].metadata["replacement_source"] == "pyDeid"
    assert "project_decimal_code_policy" not in final_spans[0].metadata


def test_deidentify_note_runs_decimal_veto_when_builtin_protected_terms_are_disabled():
    note = "Value was (189.1000043:4.002.001)."

    result = deidentify_note(note, include_builtin_protected_clinical_terms=False)

    assert result.deidentified_text == note
    assert any(
        span.metadata.get("replacement_source") == "project_decimal_code_veto"
        for span in result.spans
    )


def test_deidentify_note_preserves_decimal_code_false_positive():
    note = "Value was (189.1000043:4.002.001)."

    result = deidentify_note(note)

    assert result.deidentified_text == note
    span = next(
        span
        for span in result.spans
        if span.metadata.get("replacement_source") == "project_decimal_code_veto"
    )
    assert span.text == "(189.1000043"
    assert span.action == "preserved"


def test_deidentify_note_still_replaces_dotted_phone_number():
    note = "Call 416.555.1212 tomorrow."

    result = deidentify_note(note)

    assert "416.555.1212" not in result.deidentified_text
    assert any(span.label == "CONTACT" for span in result.spans)
    assert all(
        span.metadata.get("replacement_source") != "project_decimal_code_veto"
        for span in result.spans
    )


def test_deidentify_csv_audits_decimal_code_veto_without_raw_note_text(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    note = "Value was 189.1000043."
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-decimal-001",
                "note_id": "Note/synth-decimal-001",
                "note_text": note,
            }
        ],
    )

    summary = deidentify_csv(input_file, output_file, audit_output_file=audit_file)

    output_rows = _read_csv(output_file)
    with open(audit_file, newline="", encoding="utf-8") as handle:
        audit_rows = list(csv.DictReader(handle))
    assert summary["rows_failed"] == 0
    assert output_rows[0]["note_text"] == note
    assert audit_rows[0]["replacement_source"] == "project_decimal_code_veto"
    assert audit_rows[0]["project_decimal_code_policy"] == (
        "preserved_decimal_like_code_fragment"
    )
    assert note not in audit_file.read_text(encoding="utf-8")
