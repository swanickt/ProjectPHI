# Full-Note Smoke Tests

This folder contains local full-note smoke-test datasets used for manual
ProjectPHI review. These are not gold-standard evaluation corpora. They are
small, inspectable batches for checking end-to-end behavior, audit output, and
semantic preservation.

## Folders

### `30_synthetic_examples/`

Synthetic ProjectPHI stress-test notes generated for edge-case review.

- 30 input rows across fictional patient IDs.
- 27 expected successful output rows.
- 3 intentional missing-alias failure rows.
- Exercises stable dates, stable patient aliases, stable provider aliases,
  provider action-word preservation, protected clinical terms, custom regexes,
  contacts, identifiers, audit output, and sanitized row failures.
- Current input size: 6,815 characters total; average 227 characters / 33 words
  per note.
- Latest recorded runtime in `terminal_view.txt`: `real 0m2.710s`.
- Approximate throughput for that run: `0.090 seconds per input row`, or `0.100
  seconds per successful output row`.

See `30_synthetic_examples/README.md` for the exact command, files, and data
creation notes.

### `15_external_examples/`

Copied external de-identified sample-note bodies from the NCBI Open-Patients / TREC CDS 2016 subset, with synthetic local metadata.

- 15 input rows.
- 15 successful output rows.
- Exercises the public CLI on longer external-style de-identified clinical
  summaries with stable date shifting enabled.
- Current input size: 11,860 characters total; average 791 characters / 129
  words per note.
- Latest recorded runtime in `terminal_view.txt`: `real 0m1.612s`.
- Approximate throughput for that run: `0.107 seconds per input/output row`.

See `15_external_examples/README.md` for source notes, source metadata,
and the exact command.

## Reading The Results

Each smoke-test folder contains:

- `input_notes.csv`: source input rows/notes.
- `deidentified_output.csv`: pipeline output.
- `audit_output.csv`: internal audit rows.
- `terminal_view.txt`: captured command, summary counts, warnings, and runtime.
- `readable_review/`: generated human-readable views of the CSV artifacts.

The readable-review files are for manual inspection only. They copy note
text and audit field values exactly from the CSV artifacts, adding only
headings, grouping, indentation, and whitespace between sections.

## Timing Notes

The runtime values above are informal smoke-test timings from one local run.
They include Python startup, pyDeid import time, ProjectPHI setup, CSV I/O, and
audit writing. They should not be interpreted as benchmark results. For real
performance measurement, run repeated warm-cache trials on the target machine
and record note counts, note lengths, enabled options, and environment details.
