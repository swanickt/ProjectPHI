"""CSV adapter behavior tests.

These tests cover row-wise use of `deidentify_note(...)` while preserving CSV
columns and summaries. Privacy-specific audit assertions live separately.
"""

from datetime import date

import pytest

from project_phi import deidentify_csv
import project_phi.note as note_module
from conftest import _read_csv, _write_csv


def test_deidentify_csv_replaces_note_text_and_preserves_columns(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    rows = [
        {
            "patient_id": "Patient/synth-001",
            "encounter_id": "Encounter/synth-001",
            "note_id": "Note/synth-001",
            "note_text": "Test MRN: 011-0111. Call 416-555-1212.",
            "note_type": "synthetic",
        }
    ]
    _write_csv(input_file, rows)

    summary = deidentify_csv(input_file, output_file)

    output_rows = _read_csv(output_file)
    assert output_rows
    assert list(output_rows[0]) == list(rows[0])
    assert output_rows[0]["note_text"] != rows[0]["note_text"]
    assert output_rows[0]["note_type"] == "synthetic"
    assert output_rows[0]["patient_id"] == "Patient/synth-001"
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 1
    assert summary["rows_failed"] == 0

def test_deidentify_csv_missing_note_column_fails_clearly(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    _write_csv(input_file, [{"patient_id": "Patient/synth-003", "body": "Test MRN: 011-0111."}])

    with pytest.raises(ValueError, match="note_text"):
        deidentify_csv(input_file, output_file)

def test_deidentify_csv_rejects_audit_path_matching_input(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    _write_csv(input_file, [{"patient_id": "Patient/synth-007", "note_text": "Test MRN: 011-0111."}])

    with pytest.raises(ValueError, match="audit_output_file and input_file"):
        deidentify_csv(input_file, output_file, audit_output_file=input_file)

def test_deidentify_csv_rejects_audit_path_matching_output(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    _write_csv(input_file, [{"patient_id": "Patient/synth-008", "note_text": "Test MRN: 011-0111."}])

    with pytest.raises(ValueError, match="audit_output_file and output_file"):
        deidentify_csv(input_file, output_file, audit_output_file=output_file)

def test_deidentify_csv_passes_optional_identifiers_to_audit(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    rows = [
        {
            "patient_id": "Patient/synth-004",
            "encounter_id": "Encounter/synth-004",
            "note_id": "Note/synth-004",
            "note_text": "Test MRN: 011-0111.",
        }
    ]
    _write_csv(input_file, rows)

    deidentify_csv(input_file, output_file, audit_output_file=audit_file)

    audit_rows = _read_csv(audit_file)
    assert audit_rows
    assert audit_rows[0]["patient_id"] == "Patient/synth-004"
    assert audit_rows[0]["encounter_id"] == "Encounter/synth-004"
    assert audit_rows[0]["note_id"] == "Note/synth-004"

def test_deidentify_csv_summary_counts(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    rows = [
        {
            "patient_id": "Patient/synth-005",
            "encounter_id": "Encounter/synth-005",
            "note_id": "Note/synth-005",
            "note_text": "Test MRN: 011-0111.",
        },
        {
            "patient_id": "Patient/synth-006",
            "encounter_id": "Encounter/synth-006",
            "note_id": "Note/synth-006",
            "note_text": "No identifiers in this synthetic note.",
        },
    ]
    _write_csv(input_file, rows)

    summary = deidentify_csv(input_file, output_file, audit_output_file=audit_file)

    assert summary["rows_read"] == 2
    assert summary["rows_written"] == 2
    assert summary["rows_failed"] == 0
    assert summary["spans_written"] == len(_read_csv(audit_file))
    assert summary["warnings"] == []

def test_deidentify_csv_stable_date_shift_replaces_full_date(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    rows = [
        {
            "patient_id": "Patient/synth-csv-date-001",
            "encounter_id": "Encounter/synth-csv-date-001",
            "note_id": "Note/synth-csv-date-001",
            "note_text": "Follow-up on 2001-12-10.",
        }
    ]
    _write_csv(input_file, rows)

    summary = deidentify_csv(
        input_file,
        output_file,
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    output_rows = _read_csv(output_file)
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 1
    assert summary["rows_failed"] == 0
    assert "2001-12-10" not in output_rows[0]["note_text"]

def test_deidentify_csv_stable_date_shift_secret_env_var(tmp_path, monkeypatch):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    monkeypatch.setenv("PROJECT_PHI_CSV_DATE_SECRET", "synthetic-secret")
    rows = [
        {
            "patient_id": "Patient/synth-csv-date-002",
            "note_text": "Follow-up on 2001-12-10.",
        }
    ]
    _write_csv(input_file, rows)

    deidentify_csv(
        input_file,
        output_file,
        stable_date_shift=True,
        date_shift_secret_env_var="PROJECT_PHI_CSV_DATE_SECRET",
    )

    output_rows = _read_csv(output_file)
    assert "2001-12-10" not in output_rows[0]["note_text"]

def test_deidentify_csv_stable_date_shift_same_patient_preserves_order(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    rows = [
        {
            "patient_id": "Patient/synth-csv-date-003",
            "note_id": "Note/synth-csv-date-003a",
            "note_text": "Follow-up on 2001-12-10.",
        },
        {
            "patient_id": "Patient/synth-csv-date-003",
            "note_id": "Note/synth-csv-date-003b",
            "note_text": "Follow-up on 2002-01-09.",
        },
    ]
    _write_csv(input_file, rows)

    deidentify_csv(
        input_file,
        output_file,
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    output_rows = _read_csv(output_file)
    shifted_dates = [
        date.fromisoformat(output_rows[0]["note_text"].removeprefix("Follow-up on ").removesuffix(".")),
        date.fromisoformat(output_rows[1]["note_text"].removeprefix("Follow-up on ").removesuffix(".")),
    ]
    assert shifted_dates[1] - shifted_dates[0] == date(2002, 1, 9) - date(2001, 12, 10)
    assert shifted_dates[0] < shifted_dates[1]

def test_deidentify_csv_stable_patient_names_use_row_specific_aliases(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    rows = [
        {
            "patient_id": "Patient/synth-csv-name-001",
            "note_id": "Note/synth-csv-name-001",
            "note_text": "Patient Zylanda Qorven attended.",
        }
    ]
    _write_csv(input_file, rows)

    summary = deidentify_csv(
        input_file,
        output_file,
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={"Patient/synth-csv-name-001": ["Zylanda Qorven"]},
        patient_name_secret="synthetic-secret",
    )

    output_rows = _read_csv(output_file)
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 1
    assert summary["rows_failed"] == 0
    assert "Zylanda" not in output_rows[0]["note_text"]
    assert "Qorven" not in output_rows[0]["note_text"]

def test_deidentify_csv_stable_patient_names_residual_aliases_are_audited(
    tmp_path, monkeypatch
):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    rows = [
        {
            "patient_id": "Patient/synth-csv-residual-name-001",
            "encounter_id": "Encounter/synth-csv-residual-name-001",
            "note_id": "Note/synth-csv-residual-name-001",
            "note_text": "Patient Amelia Rowan attended. Amelia returned.",
        }
    ]
    _write_csv(input_file, rows)

    def fake_pydeid(note_text, **_kwargs):
        return [], note_text

    monkeypatch.setattr(note_module, "run_pydeid_deid_string", fake_pydeid)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={
            "Patient/synth-csv-residual-name-001": ["Amelia Rowan", "Amelia", "Rowan"]
        },
        patient_name_secret="synthetic-secret",
    )

    output_rows = _read_csv(output_file)
    audit_rows = _read_csv(audit_file)
    residual_rows = [
        row
        for row in audit_rows
        if row["replacement_source"] == "project_residual_patient_alias"
    ]
    audit_text = audit_file.read_text(encoding="utf-8")
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 1
    assert summary["rows_failed"] == 0
    assert "Amelia" not in output_rows[0]["note_text"]
    assert "Rowan" not in output_rows[0]["note_text"]
    assert len(residual_rows) == 2
    assert {row["alias_match_type"] for row in residual_rows} == {"full", "given"}
    for row in residual_rows:
        assert row["patient_id"] == "Patient/synth-csv-residual-name-001"
        assert row["encounter_id"] == "Encounter/synth-csv-residual-name-001"
        assert row["note_id"] == "Note/synth-csv-residual-name-001"
        assert row["project_name_policy"] == "residual_explicit_patient_alias"
        assert row["name_role"] == "known_patient_alias"
        assert row["project_replacement_start"]
        assert row["project_replacement_end"]
    assert "Amelia" not in audit_text
    assert "Rowan" not in audit_text

def test_deidentify_csv_passes_protected_clinical_terms_and_writes_audit(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    rows = [
        {
            "patient_id": "Patient/synth-csv-protected-001",
            "note_id": "Note/synth-csv-protected-001",
            "note_text": "Dr. Tomosynthesis reviewed the image.",
        }
    ]
    _write_csv(input_file, rows)

    summary = deidentify_csv(input_file, output_file, audit_output_file=audit_file)

    output_rows = _read_csv(output_file)
    audit_rows = _read_csv(audit_file)
    protected_rows = [
        row
        for row in audit_rows
        if row["replacement_source"] == "project_protected_clinical_term"
    ]
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 1
    assert "Tomosynthesis" in output_rows[0]["note_text"]
    assert protected_rows
    assert protected_rows[0]["action"] == "preserved"
    assert protected_rows[0]["project_replacement"] == "Tomosynthesis"
    assert protected_rows[0]["project_replacement_start"]
    assert protected_rows[0]["project_replacement_end"]
    assert protected_rows[0]["pydeid_replacement"]
    assert protected_rows[0]["project_protected_term_policy"] == "exact_normalized_span_match"
    assert protected_rows[0]["project_protected_term_rule_id"] == "breast_imaging_mammography"
    assert protected_rows[0]["project_protected_term_category"] == "breast_imaging_mammography"

def test_deidentify_csv_stable_patient_names_same_patient_consistent(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    rows = [
        {
            "patient_id": "Patient/synth-csv-name-002",
            "note_id": "Note/synth-csv-name-002a",
            "note_text": "Patient Zylanda Qorven attended.",
        },
        {
            "patient_id": "Patient/synth-csv-name-002",
            "note_id": "Note/synth-csv-name-002b",
            "note_text": "Zylanda returned.",
        },
    ]
    _write_csv(input_file, rows)

    deidentify_csv(
        input_file,
        output_file,
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={"Patient/synth-csv-name-002": ["Zylanda Qorven"]},
        patient_name_secret="synthetic-secret",
    )

    output_rows = _read_csv(output_file)
    fake_given_from_full = output_rows[0]["note_text"].removeprefix("Patient ").split()[0]
    fake_given_only = output_rows[1]["note_text"].removesuffix(" returned.")
    assert fake_given_only == fake_given_from_full

def test_deidentify_csv_stable_patient_names_different_patients_differ(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    rows = [
        {
            "patient_id": "Patient/synth-csv-name-003a",
            "note_id": "Note/synth-csv-name-003a",
            "note_text": "Patient Zylanda Qorven attended.",
        },
        {
            "patient_id": "Patient/synth-csv-name-003b",
            "note_id": "Note/synth-csv-name-003b",
            "note_text": "Patient Marvella Daxen attended.",
        },
    ]
    _write_csv(input_file, rows)

    deidentify_csv(
        input_file,
        output_file,
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={
            "Patient/synth-csv-name-003a": ["Zylanda Qorven"],
            "Patient/synth-csv-name-003b": ["Marvella Daxen"],
        },
        patient_name_secret="synthetic-secret",
    )

    output_rows = _read_csv(output_file)
    assert output_rows[0]["note_text"] != output_rows[1]["note_text"]

def test_deidentify_csv_stable_patient_names_unknown_name_uses_pydeid(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    rows = [
        {
            "patient_id": "Patient/synth-csv-name-004",
            "note_id": "Note/synth-csv-name-004",
            "note_text": "Patient Zylanda Qorven met Xavion Norel.",
        }
    ]
    _write_csv(input_file, rows)

    deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={"Patient/synth-csv-name-004": ["Zylanda Qorven"]},
        patient_name_secret="synthetic-secret",
        custom_dr_first_names={"Xavion"},
        custom_dr_last_names={"Norel"},
    )

    audit_rows = _read_csv(audit_file)
    unknown_name_rows = [
        row for row in audit_rows if row["label"] == "NAME" and row["name_role"] == "unknown_name"
    ]
    assert unknown_name_rows
    assert all(row["replacement_source"] == "pyDeid" for row in unknown_name_rows)
    assert all(row["project_name_policy"] == "unknown_name_pydeid" for row in unknown_name_rows)

def test_deidentify_csv_stable_dates_and_patient_names(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    note = "Patient Zylanda Qorven had follow-up on 2001-12-10."
    rows = [{"patient_id": "Patient/synth-csv-name-date-001", "note_text": note}]
    _write_csv(input_file, rows)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_date_shift=True,
        date_shift_secret="synthetic-date-secret",
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={"Patient/synth-csv-name-date-001": ["Zylanda Qorven"]},
        patient_name_secret="synthetic-name-secret",
    )

    output_rows = _read_csv(output_file)
    audit_rows = _read_csv(audit_file)
    assert summary["rows_read"] == 1
    assert summary["rows_written"] == 1
    assert summary["rows_failed"] == 0
    assert "2001-12-10" not in output_rows[0]["note_text"]
    assert "Zylanda" not in output_rows[0]["note_text"]
    assert "Qorven" not in output_rows[0]["note_text"]
    assert any(row["replacement_source"] == "project_stable_date_shift" for row in audit_rows)
    assert any(row["replacement_source"] == "project_stable_patient_name" for row in audit_rows)
