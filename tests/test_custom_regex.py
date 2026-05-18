"""Custom regex pass-through tests using synthetic patterns only.

These tests cover ProjectPHI's custom-regex boundary:

- ProjectPHI validates custom regex config shape and regex syntax.
- pyDeid performs the actual custom regex matching and initial replacement.
- custom regex provenance is copied into normalized span metadata.
- raw regex patterns are not copied into span metadata or audit output.
- invalid config errors are sanitized.
- custom regex spans still work when ProjectPHI reconstruction is enabled.
- CSV audit output includes safe custom-rule provenance without raw identifiers.
"""

import pytest

from project_phi import deidentify_csv, deidentify_note
from conftest import _custom_regex_config, _date_spans, _read_csv, _write_csv


def test_custom_regex_deidentify_note_uses_pydeid_custom_regex_support():
    """Custom regex config reaches pyDeid and produces safe span provenance."""
    raw_identifier = "SYN-ACC-1234"
    pattern = r"\bSYN-ACC-\d{4}\b"
    note = f"Synthetic accession {raw_identifier} reviewed."

    result = deidentify_note(note, custom_regexes=_custom_regex_config(pattern=pattern))

    custom_spans = [
        span
        for span in result.spans
        if span.metadata.get("custom_regex_rule_id") == "synthetic_accession"
    ]
    assert raw_identifier not in result.deidentified_text
    assert "<SYNTHETIC_ACCESSION>" in result.deidentified_text
    assert custom_spans
    span = custom_spans[0]
    # The configured pattern is useful for pyDeid matching but should not be
    # copied into span metadata or audit-facing fields.
    assert note[span.start : span.end] == raw_identifier
    assert span.text == raw_identifier
    assert span.replacement == "<SYNTHETIC_ACCESSION>"
    assert span.metadata["pydeid_replacement"] == "<SYNTHETIC_ACCESSION>"
    assert span.metadata["pydeid_surrogate_start"] is not None
    assert span.metadata["pydeid_surrogate_end"] is not None
    assert "Synthetic Accession" in span.pydeid_types
    assert span.metadata["custom_regex_phi_type"] == "Synthetic Accession"
    assert pattern not in str(span.metadata)

@pytest.mark.parametrize(
    "custom_regexes, message",
    [
        ({"": {"phi_type": "Synthetic Accession", "pattern": r"\bSYN-ACC-\d{4}\b"}}, "rule ID"),
        ({"synthetic_accession": {"pattern": r"\bSYN-ACC-\d{4}\b"}}, "phi_type"),
        ({"synthetic_accession": {"phi_type": "Synthetic Accession"}}, "pattern"),
        (
            {"synthetic_accession": {"phi_type": "Synthetic Accession", "pattern": r"\bSYN-ACC-("}},
            "invalid regex pattern",
        ),
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
def test_custom_regex_invalid_config_raises_sanitized_value_error(custom_regexes, message):
    """Invalid custom regex config raises without echoing notes, PHI, or patterns."""
    note = "Synthetic accession SYN-ACC-1234 reviewed."

    with pytest.raises(ValueError, match=message) as exc_info:
        deidentify_note(note, custom_regexes=custom_regexes)

    error_text = str(exc_info.value)
    # Validation errors should not echo raw note text, detected PHI, or the raw
    # regex pattern.
    assert note not in error_text
    assert "SYN-ACC-1234" not in error_text
    assert r"\bSYN-ACC-" not in error_text

def test_custom_regex_with_stable_date_shift_uses_shared_reconstruction():
    """Custom regex spans and shifted date spans share final reconstruction offsets."""
    raw_identifier = "SYN-ACC-1234"
    raw_date = "2001-12-10"
    note = f"Synthetic accession {raw_identifier} reviewed on {raw_date}."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-custom-regex-date-002",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
        custom_regexes=_custom_regex_config(),
    )

    custom_span = [
        span
        for span in result.spans
        if span.metadata.get("custom_regex_rule_id") == "synthetic_accession"
    ][0]
    date_span = _date_spans(result)[0]
    assert raw_identifier not in result.deidentified_text
    assert raw_date not in result.deidentified_text
    assert custom_span.replacement == "<SYNTHETIC_ACCESSION>"
    assert custom_span.metadata["replacement_source"] == "pyDeid"
    for span in (custom_span, date_span):
        project_start = span.metadata["project_replacement_start"]
        project_end = span.metadata["project_replacement_end"]
        assert result.deidentified_text[project_start:project_end] == span.replacement
        assert note[span.start : span.end] == span.text

def test_deidentify_csv_passes_custom_regexes_and_audits_without_raw_identifier(tmp_path):
    """CSV custom regex audit rows omit raw identifiers, note text, and patterns."""
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    raw_identifier = "SYN-ACC-1234"
    rows = [
        {
            "patient_id": "Patient/synth-custom-regex-001",
            "note_id": "Note/synth-custom-regex-001",
            "note_text": f"Synthetic accession {raw_identifier} reviewed.",
            "note_type": "synthetic",
        }
    ]
    _write_csv(input_file, rows)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        custom_regexes=_custom_regex_config(),
    )

    output_rows = _read_csv(output_file)
    audit_text = audit_file.read_text(encoding="utf-8")
    audit_rows = _read_csv(audit_file)
    custom_rows = [row for row in audit_rows if row["custom_regex_rule_id"] == "synthetic_accession"]
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 1
    assert summary["rows_failed"] == 0
    assert list(output_rows[0]) == list(rows[0])
    assert output_rows[0]["note_type"] == "synthetic"
    assert raw_identifier not in output_rows[0]["note_text"]
    assert "<SYNTHETIC_ACCESSION>" in output_rows[0]["note_text"]
    assert custom_rows
    assert custom_rows[0]["custom_regex_phi_type"] == "Synthetic Accession"
    assert custom_rows[0]["pydeid_replacement"] == "<SYNTHETIC_ACCESSION>"
    assert raw_identifier not in audit_text
    assert rows[0]["note_text"] not in audit_text
    assert r"\bSYN-ACC-\d{4}\b" not in audit_text
