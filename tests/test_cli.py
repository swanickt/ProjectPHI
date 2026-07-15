"""CLI tests for the existing CSV pipeline using synthetic inputs only."""

import csv
import json

import project_phi.cli as cli_module
from project_phi.cli import main
from conftest import _read_csv, _write_csv


def _write_alias_manifest(path, rows):
    fieldnames = ["patient_id", "alias"]
    if any("name_style" in row for row in rows):
        fieldnames.append("name_style")
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_provider_manifest(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["provider_id", "alias"])
        writer.writeheader()
        writer.writerows(rows)


def _write_custom_regex_json(path):
    path.write_text(
        json.dumps(
            {
                "synthetic_accession": {
                    "phi_type": "Synthetic Accession",
                    "pattern": r"\bSYN-ACC-\d{4}\b",
                    "replacement": "<SYNTHETIC_ACCESSION>",
                }
            }
        ),
        encoding="utf-8",
    )


def _write_protected_terms_csv(path):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["rule_id", "category", "term"])
        writer.writeheader()
        writer.writerow(
            {
                "rule_id": "synthetic_breast_imaging",
                "category": "breast_imaging",
                "term": "oncotherapia",
            }
        )


def test_cli_minimal_csv_deidentification(tmp_path, capsys):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-001",
                "note_id": "Note/synth-cli-001",
                "note_text": "Test MRN: 011-0111. Follow-up on 2001-12-10.",
            }
        ],
    )

    exit_code = main([str(input_file), str(output_file)])

    captured = capsys.readouterr()
    output_rows = _read_csv(output_file)
    assert exit_code == 0
    assert "rows_read=1" in captured.out
    assert "rows_written=1" in captured.out
    assert "rows_failed=0" in captured.out
    assert "011-0111" not in output_rows[0]["note_text"]
    assert "Test MRN: 011-0111" not in captured.out


def test_cli_stable_date_shift_uses_env_var_secret(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    monkeypatch.setenv("PROJECT_PHI_TEST_CLI_DATE_SECRET", "synthetic-date-secret")
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-date-001",
                "note_id": "Note/synth-cli-date-001",
                "note_text": "Follow-up on 2001-12-10.",
            }
        ],
    )

    exit_code = main(
        [
            str(input_file),
            str(output_file),
            "--stable-date-shift",
            "--date-shift-secret-env-var",
            "PROJECT_PHI_TEST_CLI_DATE_SECRET",
        ]
    )

    captured = capsys.readouterr()
    output_rows = _read_csv(output_file)
    assert exit_code == 0
    assert "2001-12-10" not in output_rows[0]["note_text"]
    assert "synthetic-date-secret" not in captured.out
    assert "2001-12-10" not in captured.out


def test_cli_stable_date_shift_partial_month_day_default(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    monkeypatch.setenv("PROJECT_PHI_TEST_CLI_DATE_SECRET", "synthetic-date-secret")
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-partial-date-001",
                "note_id": "Note/synth-cli-partial-date-001",
                "note_text": "Follow-up on July 15.",
            }
        ],
    )

    exit_code = main(
        [
            str(input_file),
            str(output_file),
            "--stable-date-shift",
            "--date-shift-secret-env-var",
            "PROJECT_PHI_TEST_CLI_DATE_SECRET",
        ]
    )

    captured = capsys.readouterr()
    output_rows = _read_csv(output_file)
    assert exit_code == 0
    assert "July 15" not in output_rows[0]["note_text"]
    assert "<DATE>" not in output_rows[0]["note_text"]
    assert "synthetic-date-secret" not in captured.out
    assert "July 15" not in captured.out


def test_cli_stable_date_shift_partial_month_day_disable_flag(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    monkeypatch.setenv("PROJECT_PHI_TEST_CLI_DATE_SECRET", "synthetic-date-secret")
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-partial-date-002",
                "note_id": "Note/synth-cli-partial-date-002",
                "note_text": "Follow-up on July 15.",
            }
        ],
    )

    exit_code = main(
        [
            str(input_file),
            str(output_file),
            "--stable-date-shift",
            "--date-shift-secret-env-var",
            "PROJECT_PHI_TEST_CLI_DATE_SECRET",
            "--no-shift-partial-month-day-dates",
        ]
    )

    captured = capsys.readouterr()
    output_rows = _read_csv(output_file)
    assert exit_code == 0
    assert output_rows[0]["note_text"] == "Follow-up on <DATE>."
    assert "synthetic-date-secret" not in captured.out
    assert "July 15" not in captured.out


def test_cli_stable_patient_name_surrogates_load_alias_manifest(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    manifest = tmp_path / "aliases.csv"
    monkeypatch.setenv("PROJECT_PHI_TEST_CLI_NAME_SECRET", "synthetic-name-secret")
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-name-001",
                "note_id": "Note/synth-cli-name-001",
                "note_text": "Patient Zylanda Qorven attended.",
            }
        ],
    )
    _write_alias_manifest(
        manifest,
        [{"patient_id": "Patient/synth-cli-name-001", "alias": "Zylanda Qorven"}],
    )

    exit_code = main(
        [
            str(input_file),
            str(output_file),
            "--stable-patient-name-surrogates",
            "--patient-alias-manifest",
            str(manifest),
            "--patient-name-secret-env-var",
            "PROJECT_PHI_TEST_CLI_NAME_SECRET",
        ]
    )

    captured = capsys.readouterr()
    output_rows = _read_csv(output_file)
    assert exit_code == 0
    assert "Zylanda" not in output_rows[0]["note_text"]
    assert "Qorven" not in output_rows[0]["note_text"]
    assert "Zylanda" not in captured.out
    assert "Qorven" not in captured.out
    assert "synthetic-name-secret" not in captured.out


def test_cli_stable_patient_name_surrogates_loads_name_style(
    tmp_path,
    monkeypatch,
    capsys,
):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    manifest = tmp_path / "aliases.csv"
    monkeypatch.setenv("PROJECT_PHI_TEST_CLI_NAME_SECRET", "synthetic-name-secret")
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-name-style-001",
                "note_id": "Note/synth-cli-name-style-001",
                "note_text": "Patient Zylanda Qorven attended.",
            }
        ],
    )
    _write_alias_manifest(
        manifest,
        [
            {
                "patient_id": "Patient/synth-cli-name-style-001",
                "alias": "Zylanda Qorven",
                "name_style": "feminine",
            }
        ],
    )

    exit_code = main(
        [
            str(input_file),
            str(output_file),
            "--audit-output-file",
            str(audit_file),
            "--stable-patient-name-surrogates",
            "--patient-alias-manifest",
            str(manifest),
            "--patient-name-secret-env-var",
            "PROJECT_PHI_TEST_CLI_NAME_SECRET",
        ]
    )

    captured = capsys.readouterr()
    audit_rows = _read_csv(audit_file)
    stable_rows = [
        row
        for row in audit_rows
        if row["replacement_source"] == "project_stable_patient_name"
    ]
    assert exit_code == 0
    assert stable_rows
    assert {row["patient_name_style"] for row in stable_rows} == {"feminine"}
    assert "Zylanda" not in captured.out
    assert "feminine" not in captured.out


def test_cli_stable_provider_name_surrogates_load_provider_manifest(
    tmp_path,
    monkeypatch,
    capsys,
):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    manifest = tmp_path / "providers.csv"
    monkeypatch.setenv("PROJECT_PHI_TEST_CLI_PROVIDER_SECRET", "synthetic-provider-secret")
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-provider-001",
                "note_id": "Note/synth-cli-provider-001",
                "note_text": "Radiologist Chen reviewed mammography.",
            }
        ],
    )
    _write_provider_manifest(
        manifest,
        [{"provider_id": "Provider/synth-cli-chen", "alias": "Chen"}],
    )

    exit_code = main(
        [
            str(input_file),
            str(output_file),
            "--stable-provider-name-surrogates",
            "--provider-alias-manifest",
            str(manifest),
            "--provider-name-secret-env-var",
            "PROJECT_PHI_TEST_CLI_PROVIDER_SECRET",
        ]
    )

    captured = capsys.readouterr()
    output_rows = _read_csv(output_file)
    assert exit_code == 0
    assert "Radiologist Chen" not in output_rows[0]["note_text"]
    assert "Radiologist " in output_rows[0]["note_text"]
    assert "Chen" not in captured.out
    assert "synthetic-provider-secret" not in captured.out


def test_cli_stable_unknown_name_surrogates_uses_env_var_secret(
    tmp_path,
    monkeypatch,
    capsys,
):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    monkeypatch.setenv("PROJECT_PHI_TEST_CLI_UNKNOWN_SECRET", "synthetic-unknown-secret")
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-unknown-001",
                "note_id": "Note/synth-cli-unknown-001a",
                "note_text": "Maria Lopez called.",
            },
            {
                "patient_id": "Patient/synth-cli-unknown-001",
                "note_id": "Note/synth-cli-unknown-001b",
                "note_text": "Maria called again.",
            },
        ],
    )

    exit_code = main(
        [
            str(input_file),
            str(output_file),
            "--stable-unknown-name-surrogates",
            "--unknown-name-secret-env-var",
            "PROJECT_PHI_TEST_CLI_UNKNOWN_SECRET",
        ]
    )

    captured = capsys.readouterr()
    output_rows = _read_csv(output_file)
    assert exit_code == 0
    assert "rows_read=2" in captured.out
    assert "rows_written=2" in captured.out
    assert "synthetic-unknown-secret" not in captured.out
    assert "Maria" not in captured.out
    assert len(output_rows) == 2


def test_cli_stable_unknown_name_surrogates_requires_secret_env_var(
    tmp_path,
    capsys,
):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-unknown-002",
                "note_id": "Note/synth-cli-unknown-002",
                "note_text": "Maria Lopez called.",
            }
        ],
    )

    exit_code = main(
        [
            str(input_file),
            str(output_file),
            "--stable-unknown-name-surrogates",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--unknown-name-secret-env-var" in captured.err


def test_cli_custom_regex_json_removes_synthetic_identifier_without_printing_config(
    tmp_path,
    capsys,
):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    config = tmp_path / "custom_regexes.json"
    raw_identifier = "SYN-ACC-1234"
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-regex-001",
                "note_id": "Note/synth-cli-regex-001",
                "note_text": f"Synthetic accession {raw_identifier} reviewed.",
            }
        ],
    )
    _write_custom_regex_json(config)

    exit_code = main(
        [
            str(input_file),
            str(output_file),
            "--custom-regex-json",
            str(config),
        ]
    )

    captured = capsys.readouterr()
    output_rows = _read_csv(output_file)
    assert exit_code == 0
    assert raw_identifier not in output_rows[0]["note_text"]
    assert "<SYNTHETIC_ACCESSION>" in output_rows[0]["note_text"]
    assert raw_identifier not in captured.out
    assert r"\bSYN-ACC-\d{4}\b" not in captured.out


def test_cli_protected_clinical_terms_csv_preserves_term_without_printing_config(
    tmp_path,
    capsys,
):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    config = tmp_path / "protected_terms.csv"
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-protected-001",
                "note_id": "Note/synth-cli-protected-001",
                "note_text": "Dr. Oncotherapia reviewed the image.",
            }
        ],
    )
    _write_protected_terms_csv(config)

    exit_code = main(
        [
            str(input_file),
            str(output_file),
            "--protected-clinical-terms-csv",
            str(config),
        ]
    )

    captured = capsys.readouterr()
    output_rows = _read_csv(output_file)
    assert exit_code == 0
    assert "Oncotherapia" in output_rows[0]["note_text"]
    assert "rows_read=1" in captured.out
    assert "oncotherapia" not in captured.out.casefold()
    assert "Dr. Oncotherapia reviewed" not in captured.out


def test_cli_missing_required_stable_config_returns_nonzero_and_sanitized(capsys, tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-error-001",
                "note_id": "Note/synth-cli-error-001",
                "note_text": "Patient Zylanda Qorven attended.",
            }
        ],
    )

    exit_code = main([str(input_file), str(output_file), "--stable-patient-name-surrogates"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "--patient-alias-manifest" in captured.err
    assert "Zylanda" not in captured.err
    assert "Qorven" not in captured.err
    assert "Patient Zylanda Qorven" not in captured.out


def test_cli_missing_provider_manifest_returns_nonzero_and_sanitized(capsys, tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-provider-error-001",
                "note_id": "Note/synth-cli-provider-error-001",
                "note_text": "Radiologist Chen reviewed mammography.",
            }
        ],
    )

    exit_code = main([str(input_file), str(output_file), "--stable-provider-name-surrogates"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "--provider-alias-manifest" in captured.err
    assert "Chen" not in captured.err
    assert "Radiologist Chen" not in captured.out


def test_cli_preflight_import_failure_fails_before_row_processing(
    tmp_path,
    monkeypatch,
    capsys,
):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-cli-preflight-001",
                "note_id": "Note/synth-cli-preflight-001",
                "note_text": "Patient Zylanda Qorven attended.",
            }
        ],
    )

    def fail_preflight():
        raise RuntimeError(
            "pyDeid is not importable. Please install pyDeid from the pinned "
            "project dependency. Underlying import error: ModuleNotFoundError: "
            "No module named 'click'"
        )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("deidentify_csv should not run after preflight failure")

    monkeypatch.setattr(cli_module, "preflight_pydeid_import", fail_preflight)
    monkeypatch.setattr(cli_module, "deidentify_csv", fail_if_called)

    exit_code = main([str(input_file), str(output_file)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "pyDeid is not importable" in captured.err
    assert "ModuleNotFoundError" in captured.err
    assert "No module named 'click'" in captured.err
    assert "Zylanda" not in captured.err
    assert "Qorven" not in captured.err
    assert not output_file.exists()
