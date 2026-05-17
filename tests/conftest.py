"""Shared synthetic test helpers.

All test examples are synthetic. These helpers keep repeated CSV setup and span
queries small while avoiding real PHI and real site-specific identifier formats.
"""

import csv


def _write_csv(path, rows):
    """Write test rows to a UTF-8 CSV file.

    Args:
        path: Output CSV path.
        rows: Nonempty list of dictionaries with the same keys. The first row's
            keys define the CSV header order.
    """
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path):
    """Read a UTF-8 CSV file into a list of row dictionaries."""
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _custom_regex_config(pattern=r"\bSYN-ACC-\d{4}\b"):
    """Return a synthetic custom-regex config used by tests.

    The default pattern matches fake accession-like values such as
    `SYN-ACC-1234`. It is intentionally synthetic and not a real local
    identifier format.
    """
    return {
        "synthetic_accession": {
            "phi_type": "Synthetic Accession",
            "pattern": pattern,
            "replacement": "<SYNTHETIC_ACCESSION>",
        }
    }


def _date_spans(result):
    """Return spans normalized to the broad `DATE` label."""
    return [span for span in result.spans if span.label == "DATE"]


def _name_spans(result):
    """Return spans normalized to the broad `NAME` label."""
    return [span for span in result.spans if span.label == "NAME"]


def _stable_patient_name_spans(result):
    """Return name spans replaced by ProjectPHI's stable patient-name policy."""
    return [
        span
        for span in _name_spans(result)
        if span.metadata.get("replacement_source") == "project_stable_patient_name"
    ]