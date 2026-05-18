"""CLI tests for the CSV pipeline using synthetic inputs only.

These tests cover the command-line wrapper around `deidentify_csv(...)`.

Main contracts covered:
- the CLI can run the basic CSV de-identification workflow;
- stable date shifting uses a secret supplied through an environment variable;
- stable patient-name surrogates load aliases from a manifest CSV;
- custom regex JSON config is loaded without printing raw patterns;
- protected clinical terms CSV config is loaded without printing term lists;
- missing required flag combinations return a nonzero exit code;
- CLI stdout/stderr contain sanitized counts/errors, not notes, aliases,
  secrets, regex patterns, detected PHI, or raw config contents.

These tests use synthetic notes, identifiers, aliases, and config files only.
"""

import csv
import json

from project_phi.cli import main
from conftest import _read_csv, _write_csv


def _write_alias_manifest(path, rows):
    """Write a synthetic patient-alias manifest for CLI tests.

    The manifest shape matches the runtime loader expectation:

        patient_id,alias

    Example row:
        Patient/synth-cli-name-001,Zylanda Qorven
    """
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["patient_id", "alias"])
        writer.writeheader()
        writer.writerows(rows)


def _write_custom_regex_json(path):
    """Write a synthetic custom-regex config for CLI tests.

    The pattern matches fake accession-like values such as `SYN-ACC-1234`.
    It is intentionally synthetic and should not appear in CLI output.
    """
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
    """Write a synthetic protected-term CSV for CLI tests.

    The term `oncotherapia` is fake clinical-looking text used to verify that
    protected-term config can preserve a pyDeid-emitted span without printing
    the configured term list to stdout/stderr.
    """
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
    """The CLI de-identifies a CSV and prints sanitized summary counts."""
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
    """Stable date shifting uses an env-var secret name without printing the secret."""
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


def test_cli_stable_patient_name_surrogates_load_alias_manifest(tmp_path, monkeypatch, capsys):
    """Stable patient-name mode loads aliases from CSV without printing aliases or secrets."""
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


def test_cli_custom_regex_json_removes_synthetic_identifier_without_printing_config(
    tmp_path,
    capsys,
):
    """Custom regex config removes a synthetic identifier without printing config details."""
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
    """Protected-term CSV config preserves a term without printing the configured term."""
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
    """Missing required stable-name flags fail without printing row note contents."""
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