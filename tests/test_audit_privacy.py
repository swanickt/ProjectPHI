"""Audit and warning privacy tests.

These tests focus on making sure raw synthetic note text, raw detected PHI,
raw aliases, and raw regex-like values do not leak into audit/warning outputs.
"""

from project_phi import DeidentificationResult, deidentify_csv
import project_phi.csv_adapter as csv_adapter
from conftest import _read_csv, _write_csv


def test_deidentify_csv_writes_audit_without_raw_note_text(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    raw_identifier = "011-0111"
    rows = [
        {
            "patient_id": "Patient/synth-002",
            "encounter_id": "Encounter/synth-002",
            "note_id": "Note/synth-002",
            "note_text": f"Test MRN: {raw_identifier}. Call 416-555-1212.",
        }
    ]
    _write_csv(input_file, rows)

    summary = deidentify_csv(input_file, output_file, audit_output_file=audit_file)

    audit_text = audit_file.read_text(encoding="utf-8")
    audit_rows = _read_csv(audit_file)
    assert audit_rows
    # Audit rows carry metadata and replacements, but not raw detected PHI or
    # full note text.
    assert raw_identifier not in audit_text
    assert rows[0]["note_text"] not in audit_text
    assert all("pydeid_types" in row for row in audit_rows)
    assert all("pydeid_replacement" in row for row in audit_rows)
    assert all("project_replacement" in row for row in audit_rows)
    assert all("replacement" not in row for row in audit_rows)
    assert all("surrogate_start" not in row for row in audit_rows)
    assert all("surrogate_end" not in row for row in audit_rows)
    assert summary["spans_written"] == len(audit_rows)

def test_deidentify_csv_row_failure_is_sanitized_and_omitted(tmp_path, monkeypatch):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    failed_note = "FAILME synthetic MRN 011-0111."
    rows = [
        {
            "patient_id": "Patient/synth-009",
            "encounter_id": "Encounter/synth-009",
            "note_id": "Note/synth-009",
            "note_text": failed_note,
        },
        {
            "patient_id": "Patient/synth-010",
            "encounter_id": "Encounter/synth-010",
            "note_id": "Note/synth-010",
            "note_text": "No identifiers in this synthetic note.",
        },
    ]
    _write_csv(input_file, rows)

    def fake_deidentify_note(note_text, **kwargs):
        if note_text == failed_note:
            # The fake exception includes raw note text to prove the CSV adapter
            # copies only sanitized exception class metadata.
            raise RuntimeError(f"failure while processing {note_text}")
        return DeidentificationResult(
            original_text=None,
            deidentified_text="Deidentified synthetic note.",
            spans=[],
            warnings=[],
            metadata=kwargs,
        )

    monkeypatch.setattr(csv_adapter, "deidentify_note", fake_deidentify_note)

    summary = deidentify_csv(input_file, output_file, audit_output_file=audit_file)

    output_rows = _read_csv(output_file)
    audit_text = audit_file.read_text(encoding="utf-8")
    audit_rows = _read_csv(audit_file)
    warning_text = " ".join(summary["warnings"])
    # Failed rows are omitted, and warning/audit text must remain sanitized.
    assert summary["rows_read"] == 2
    assert summary["rows_written"] == 1
    assert summary["rows_failed"] == 1
    assert len(output_rows) == 1
    assert output_rows[0]["patient_id"] == "Patient/synth-010"
    assert failed_note not in audit_text
    assert "011-0111" not in audit_text
    assert failed_note not in warning_text
    assert "011-0111" not in warning_text
    assert "RuntimeError" in warning_text
    assert audit_rows[0]["custom_regex_rule_id"] == ""
    assert audit_rows[0]["custom_regex_phi_type"] == ""
    assert audit_rows[0]["project_protected_term_policy"] == ""
    assert audit_rows[0]["project_protected_term_rule_id"] == ""
    assert audit_rows[0]["project_protected_term_category"] == ""
    assert audit_rows[0]["project_protected_component"] == ""
    assert audit_rows[0]["project_protected_within_phrase"] == ""
    assert audit_rows[0]["project_title_context_policy"] == ""
    assert audit_rows[0]["project_title_context_trigger"] == ""
    assert audit_rows[0]["project_title_context_word"] == ""
    assert audit_rows[0]["project_title_token_policy"] == ""
    assert audit_rows[0]["project_title_token"] == ""
    assert audit_rows[0]["project_title_token_context"] == ""
    assert audit_rows[0]["project_ordinary_token_policy"] == ""
    assert audit_rows[0]["project_ordinary_token"] == ""
    assert audit_rows[0]["project_ordinary_token_category"] == ""
    assert audit_rows[0]["project_clinical_abbreviation_policy"] == ""
    assert audit_rows[0]["project_clinical_abbreviation"] == ""
    assert audit_rows[0]["project_clinical_abbreviation_context"] == ""
    assert audit_rows[0]["project_obstetric_history_policy"] == ""
    assert audit_rows[0]["project_obstetric_history_pattern"] == ""

def test_deidentify_csv_stable_date_shift_audit_metadata_without_raw_phi(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    raw_date = "2001-12-10"
    raw_identifier = "011-0111"
    rows = [
        {
            "patient_id": "Patient/synth-csv-date-004",
            "encounter_id": "Encounter/synth-csv-date-004",
            "note_id": "Note/synth-csv-date-004",
            "note_text": f"Test MRN: {raw_identifier}. Follow-up on {raw_date}.",
        }
    ]
    _write_csv(input_file, rows)

    deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    audit_text = audit_file.read_text(encoding="utf-8")
    audit_rows = _read_csv(audit_file)
    date_rows = [row for row in audit_rows if row["label"] == "DATE"]
    assert date_rows
    date_row = date_rows[0]
    assert date_row["replacement_source"] == "project_stable_date_shift"
    assert date_row["project_replacement"]
    assert date_row["project_replacement_start"]
    assert date_row["project_replacement_end"]
    assert date_row["pydeid_replacement"]
    assert date_row["pydeid_surrogate_start"]
    assert date_row["pydeid_surrogate_end"]
    assert date_row["project_date_shift_policy"] == "shifted_full_date"
    non_date_rows = [row for row in audit_rows if row["label"] != "DATE"]
    assert non_date_rows
    for row in non_date_rows:
        assert row["project_date_shift_policy"] == ""
        assert row["project_date_shift_range_days"] == ""
        assert row["project_date_shift_days"] == ""
    assert raw_date not in audit_text
    assert raw_identifier not in audit_text

def test_deidentify_csv_stable_date_shift_missing_patient_id_row_fails_safely(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    failed_note = "Follow-up on 2001-12-10."
    rows = [
        {
            "patient_id": "",
            "note_id": "Note/synth-csv-date-005a",
            "note_text": failed_note,
        },
        {
            "patient_id": "Patient/synth-csv-date-005",
            "note_id": "Note/synth-csv-date-005b",
            "note_text": "Follow-up on 2002-01-09.",
        },
    ]
    _write_csv(input_file, rows)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    output_rows = _read_csv(output_file)
    audit_text = audit_file.read_text(encoding="utf-8")
    warning_text = " ".join(summary["warnings"])
    assert summary["rows_read"] == 2
    assert summary["rows_written"] == 1
    assert summary["rows_failed"] == 1
    assert len(output_rows) == 1
    assert output_rows[0]["patient_id"] == "Patient/synth-csv-date-005"
    assert failed_note not in audit_text
    assert "2001-12-10" not in audit_text
    assert failed_note not in warning_text
    assert "2001-12-10" not in warning_text
    assert "ValueError" in warning_text

def test_deidentify_csv_stable_date_shift_types_excluding_dates_fail_safely(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    note = "Test MRN: 011-0111. Follow-up on 2001-12-10."
    rows = [
        {
            "patient_id": "Patient/synth-csv-date-006",
            "note_id": "Note/synth-csv-date-006",
            "note_text": note,
        }
    ]
    _write_csv(input_file, rows)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
        types=["mrn"],
    )

    output_rows = _read_csv(output_file)
    audit_text = audit_file.read_text(encoding="utf-8")
    warning_text = " ".join(summary["warnings"])
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 0
    assert summary["rows_failed"] == 1
    assert output_rows == []
    assert note not in audit_text
    assert "2001-12-10" not in audit_text
    assert "011-0111" not in audit_text
    assert note not in warning_text
    assert "2001-12-10" not in warning_text
    assert "011-0111" not in warning_text
    assert "ValueError" in warning_text

def test_deidentify_csv_stable_date_shift_missing_secret_fails_safely(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    note = "Test MRN: 011-0111. Follow-up on 2001-12-10."
    rows = [
        {
            "patient_id": "Patient/synth-csv-date-007",
            "note_id": "Note/synth-csv-date-007",
            "note_text": note,
        }
    ]
    _write_csv(input_file, rows)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_date_shift=True,
    )

    output_rows = _read_csv(output_file)
    audit_text = audit_file.read_text(encoding="utf-8")
    warning_text = " ".join(summary["warnings"])
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 0
    assert summary["rows_failed"] == 1
    assert output_rows == []
    assert note not in audit_text
    assert "2001-12-10" not in audit_text
    assert "011-0111" not in audit_text
    assert note not in warning_text
    assert "2001-12-10" not in warning_text
    assert "011-0111" not in warning_text
    assert "ValueError" in warning_text

def test_deidentify_csv_stable_patient_name_audit_metadata_without_raw_phi(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    raw_given = "Zylanda"
    raw_family = "Qorven"
    rows = [
        {
            "patient_id": "Patient/synth-csv-name-005",
            "encounter_id": "Encounter/synth-csv-name-005",
            "note_id": "Note/synth-csv-name-005",
            "note_text": f"Patient {raw_given} {raw_family} attended.",
        }
    ]
    _write_csv(input_file, rows)

    deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={"Patient/synth-csv-name-005": [f"{raw_given} {raw_family}"]},
        patient_name_secret="synthetic-secret",
    )

    audit_text = audit_file.read_text(encoding="utf-8")
    audit_rows = _read_csv(audit_file)
    stable_name_rows = [
        row
        for row in audit_rows
        if row["replacement_source"] == "project_stable_patient_name"
    ]
    assert stable_name_rows
    for row in stable_name_rows:
        assert row["project_replacement"]
        assert row["project_replacement_start"]
        assert row["project_replacement_end"]
        assert row["pydeid_replacement"]
        assert row["pydeid_surrogate_start"]
        assert row["pydeid_surrogate_end"]
        assert row["project_name_policy"] == "known_patient_alias"
        assert row["name_role"] == "known_patient_alias"
        assert row["alias_match_type"] in {"given", "family"}
    assert raw_given not in audit_text
    assert raw_family not in audit_text
    assert rows[0]["note_text"] not in audit_text

def test_deidentify_csv_stable_patient_names_missing_aliases_fail_safely(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    note = "Patient Zylanda Qorven attended."
    rows = [
        {
            "patient_id": "Patient/synth-csv-name-006",
            "note_id": "Note/synth-csv-name-006",
            "note_text": note,
        }
    ]
    _write_csv(input_file, rows)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={"Patient/synth-csv-name-other": ["Zylanda Qorven"]},
        patient_name_secret="synthetic-secret",
    )

    output_rows = _read_csv(output_file)
    audit_text = audit_file.read_text(encoding="utf-8")
    audit_rows = _read_csv(audit_file)
    warning_text = " ".join(summary["warnings"])
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 0
    assert summary["rows_failed"] == 1
    assert output_rows == []
    assert len(audit_rows) == 1
    assert audit_rows[0]["project_name_policy"] == ""
    assert audit_rows[0]["name_role"] == ""
    assert audit_rows[0]["alias_match_type"] == ""
    assert note not in audit_text
    assert "Zylanda" not in audit_text
    assert "Qorven" not in audit_text
    assert note not in warning_text
    assert "Zylanda" not in warning_text
    assert "Qorven" not in warning_text
    assert "ValueError" in warning_text

def test_deidentify_csv_stable_patient_names_missing_patient_id_fails_safely(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    note = "Patient Zylanda Qorven has MRN 011-0111."
    rows = [
        {
            "patient_id": "",
            "note_id": "Note/synth-csv-name-006b",
            "note_text": note,
        }
    ]
    _write_csv(input_file, rows)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={"Patient/synth-csv-name-006b": ["Zylanda Qorven"]},
        patient_name_secret="synthetic-secret",
    )

    output_rows = _read_csv(output_file)
    audit_text = audit_file.read_text(encoding="utf-8")
    audit_rows = _read_csv(audit_file)
    warning_text = " ".join(summary["warnings"])
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 0
    assert summary["rows_failed"] == 1
    assert output_rows == []
    assert len(audit_rows) == 1
    assert audit_rows[0]["project_name_policy"] == ""
    assert audit_rows[0]["name_role"] == ""
    assert audit_rows[0]["alias_match_type"] == ""
    assert note not in audit_text
    assert "Zylanda" not in audit_text
    assert "Qorven" not in audit_text
    assert "011-0111" not in audit_text
    assert note not in warning_text
    assert "Zylanda" not in warning_text
    assert "Qorven" not in warning_text
    assert "011-0111" not in warning_text
    assert "ValueError" in warning_text

def test_deidentify_csv_stable_patient_names_missing_alias_map_fails_safely(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    note = "Patient Zylanda Qorven attended."
    rows = [{"patient_id": "Patient/synth-csv-name-007", "note_text": note}]
    _write_csv(input_file, rows)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_patient_name_surrogates=True,
        patient_name_secret="synthetic-secret",
    )

    assert summary["rows_written"] == 0
    assert summary["rows_failed"] == 1
    assert _read_csv(output_file) == []
    assert note not in audit_file.read_text(encoding="utf-8")
    assert "ValueError" in " ".join(summary["warnings"])

def test_deidentify_csv_stable_patient_names_ambiguous_aliases_fail_safely(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    note = "Patient Jordan has MRN 011-0111."
    rows = [{"patient_id": "Patient/synth-csv-name-007b", "note_text": note}]
    aliases = ["Jordan Smith", "Alex Jordan", "Jordan"]
    _write_csv(input_file, rows)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={"Patient/synth-csv-name-007b": aliases},
        patient_name_secret="synthetic-secret",
    )

    output_rows = _read_csv(output_file)
    audit_text = audit_file.read_text(encoding="utf-8")
    audit_rows = _read_csv(audit_file)
    warning_text = " ".join(summary["warnings"])
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 0
    assert summary["rows_failed"] == 1
    assert output_rows == []
    assert len(audit_rows) == 1
    assert audit_rows[0]["project_name_policy"] == ""
    assert audit_rows[0]["name_role"] == ""
    assert audit_rows[0]["alias_match_type"] == ""
    assert note not in audit_text
    assert "Jordan" not in audit_text
    assert "Smith" not in audit_text
    assert "Alex" not in audit_text
    assert "011-0111" not in audit_text
    assert note not in warning_text
    assert "Jordan" not in warning_text
    assert "Smith" not in warning_text
    assert "Alex" not in warning_text
    assert "011-0111" not in warning_text
    assert "ValueError" in warning_text

def test_deidentify_csv_stable_patient_names_missing_env_secret_fails_safely(tmp_path, monkeypatch):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    note = "Patient Zylanda Qorven attended."
    rows = [{"patient_id": "Patient/synth-csv-name-008", "note_text": note}]
    _write_csv(input_file, rows)
    monkeypatch.delenv("PROJECT_PHI_MISSING_CSV_NAME_SECRET", raising=False)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={"Patient/synth-csv-name-008": ["Zylanda Qorven"]},
        patient_name_secret_env_var="PROJECT_PHI_MISSING_CSV_NAME_SECRET",
    )

    assert summary["rows_written"] == 0
    assert summary["rows_failed"] == 1
    assert note not in audit_file.read_text(encoding="utf-8")
    assert "ValueError" in " ".join(summary["warnings"])

    monkeypatch.setenv("PROJECT_PHI_EMPTY_CSV_NAME_SECRET", "")
    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={"Patient/synth-csv-name-008": ["Zylanda Qorven"]},
        patient_name_secret_env_var="PROJECT_PHI_EMPTY_CSV_NAME_SECRET",
    )
    assert summary["rows_written"] == 0
    assert summary["rows_failed"] == 1

def test_deidentify_csv_stable_patient_names_types_excluding_names_fail_safely(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    note = "Patient Zylanda Qorven attended."
    rows = [{"patient_id": "Patient/synth-csv-name-009", "note_text": note}]
    _write_csv(input_file, rows)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={"Patient/synth-csv-name-009": ["Zylanda Qorven"]},
        patient_name_secret="synthetic-secret",
        types=["dates"],
    )

    assert summary["rows_written"] == 0
    assert summary["rows_failed"] == 1
    assert _read_csv(output_file) == []
    assert note not in audit_file.read_text(encoding="utf-8")
    assert "ValueError" in " ".join(summary["warnings"])
