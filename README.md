# ProjectPHI

ProjectPHI is an Ontario/Canadian clinical free-text
de-identification pipeline built around
[`pyDeid`](https://github.com/GEMINI-Medicine/pyDeid).

It is designed for governed research workflows that need identifier risk
reduction before review and possible model-training candidate preparation.
The project removes concrete identifiers while preserving clinically meaningful
language where possible.

ProjectPHI is not a legal certification tool. It does not claim full
de-identification, anonymization, PHIPA compliance, HIPAA compliance, or
external-release safety.

## Acknowledgements And Maintainer

ProjectPHI is built on pyDeid from GEMINI Medicine. pyDeid provides the core
PHI detection, pruning, and fallback replacement behavior. ProjectPHI adds
project-specific reconstruction, audit, date-shifting, alias-stability, and
semantic-preservation behavior for governed Ontario clinical text workflows.

ProjectPHI is maintained by Thomas Swanick
<thomas.swanick@mail.utoronto.ca>.

## Documentation

Start with [docs/00_index.md](docs/00_index.md).

Key pages:

- [Pipeline overview](docs/01_pipeline_overview.md)
- [Architecture](docs/02_architecture.md)
- [pyDeid behaviour](docs/03_pydeid_behaviour.md)
- [ProjectPHI behaviour](docs/04_ProjectPHI_behaviour.md)
- [Configuration](docs/05_configuration.md)
- [Privacy and audit notes](docs/06_privacy_and_audit_notes.md)
- [Semantic preservation](docs/07_semantic_preservation.md)
- [Examples](docs/08_examples.md)
- [Current limitations](docs/09_current_limitations.md)

## Current Capabilities

- Single-note de-identification with `deidentify_note(...)`.
- Per-patient timeline de-identification with `deidentify_patient_notes(...)`
  for Python callers that need batch-stable unknown-name surrogates.
- CSV de-identification with `deidentify_csv(...)` and `project-phi-deid`.
- pyDeid-first PHI detection, pruning, custom regex matching, custom name-list
  handling, and initial surrogate generation.
- Normalized `PHISpan` records with original-note offsets, pyDeid surrogate
  metadata, and project-final replacement metadata kept separate.
- Stable per-patient date shifting for pyDeid-detected parseable full dates,
  month/year spans, and month/day spans.
- Public patient-specific date-shift offset helper for downstream tabular date
  shifting.
- Stable patient-name surrogates for explicit patient aliases, including a
  bounded exact residual pass for supplied aliases that pyDeid prunes before
  ProjectPHI sees them.
- Stable provider-name surrogates for explicit governed provider aliases,
  including role-guarded residual matching for single-token aliases.
- Optional patient-local stable unknown-name surrogates for Python batch and
  grouped CSV/CLI workflows. This does not infer names; it only stabilizes
  remaining pyDeid-detected `NAME` spans within one patient's supplied notes.
- Protected clinical-term and narrow title/context false-positive vetoes for
  observed semantic-preservation failures.
- Dotted decimal-like contact false-positive vetoes for code/measurement
  fragments that pyDeid emits as phone-like spans.
- Compact clinical-code and phrase vetoes for strongly contextual scores,
  stages, biomedical abbreviations, and duration/exposure phrases.
- Ordinary clinical prose and vendor/reference metadata vetoes that avoid
  preserving geography by default.
- Runtime config loaders for patient alias manifests, provider alias manifests,
  custom regex JSON, and protected clinical terms CSV.
- Internal audit CSV output for span-level review.

## What It Does Not Do

- It does not use NER, LLMs, external APIs, or a separate PHI detector.
- It does not bundle pyDeid inside the `project_phi` package.
- It does not ship Ontario site-specific regexes, provider lists, facility
  lists, patient lists, local geography lists, or broad gazetteers. It does
  include a curated non-site-specific protected clinical-term inventory for
  semantic preservation.
- It does not guarantee that every sensitive phrase is removed.
- It does not make outputs safe for external release by itself.

## Installation

Clone the repository:

```bash
git clone <repo-url>
cd project_phi
```

ProjectPHI uses `uv` for the recommended lab-local setup. If `uv` is not
installed:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Create a Python 3.11 environment and install the project:

```bash
uv venv .venv --python 3.11
source .venv/bin/activate
uv sync --extra dev
```

The first sync needs internet access because `uv` fetches pyDeid from the
pinned GitHub commit in `pyproject.toml` / `uv.lock` and resolves Python
dependencies from the configured package index. Returning to an already-created
environment does not need internet for normal local runs unless the environment
is rebuilt or dependency pins change.

The current pyDeid stack also uses compatibility pins declared in
`pyproject.toml`, including `setuptools<81` for pyDeid's `pkg_resources` import
and `numpy<2` for the tested spaCy/thinc stack.

## Python Quick Start

```python
from project_phi import deidentify_note

note = "Test MRN: 011-0111. Follow-up on 2001-12-10."

result = deidentify_note(
    note,
    patient_id="Patient/synthetic-001",
    note_id="Note/synthetic-001",
    stable_date_shift=True,
    date_shift_secret="synthetic-demo-secret",
)

print(result.deidentified_text)
for span in result.spans:
    print(span.label, span.start, span.end, span.pydeid_types, span.replacement)
    print(span.metadata.get("replacement_source"))
    print(span.metadata.get("project_date_shift_policy"))
```

Observed output from the current environment:

```text
deidentified_text:
Test MRN: 4648190. Follow-up on 2001-11-20.

spans:
ID 10 18 ['MRN'] 4648190
pyDeid
pydeid_replacement
DATE 33 43 ['Year/Month/Day [yy(yy)/mm/dd]'] 2001-11-20
project_stable_date_shift
shifted_full_date
```

`PHISpan.start` and `PHISpan.end` are offsets into the original note. pyDeid
surrogate offsets and project-final replacement offsets live in separate span
metadata fields.

## Patient Timeline Batch Quick Start

```python
from project_phi import deidentify_patient_notes

batch = deidentify_patient_notes(
    [
        {"note_id": "n1", "note_text": "Maria Lopez called."},
        {"note_id": "n2", "note_text": "Maria called again."},
    ],
    patient_id="Patient/synthetic-003",
    stable_date_shift=True,
    date_shift_secret="synthetic-date-secret",
    stable_unknown_name_surrogates=True,
    unknown_name_secret="synthetic-name-secret",
)

for result in batch.results:
    print(result.metadata["note_id"], result.deidentified_text)
```

This Python-only batch API is for one patient at a time. Explicit patient and
provider aliases still take priority when enabled. Unknown-name stabilization
applies only to remaining pyDeid-detected name spans in the supplied batch.

CSV and CLI workflows can also opt into grouped patient timeline processing
with `stable_unknown_name_surrogates=True` or
`--stable-unknown-name-surrogates`. In that mode rows are grouped by
`patient_id`, processed per patient, and written back in the original row order.

## CSV And CLI Quick Start

```python
from project_phi import deidentify_csv

summary = deidentify_csv(
    "synthetic_input.csv",
    "synthetic_output.csv",
    audit_output_file="synthetic_audit.csv",
)
print(summary)
```

Using this synthetic input:

```csv
patient_id,note_id,note_text
Patient/synthetic-csv-001,Note/synthetic-csv-001,Test MRN: 011-0111. Call 416-555-1212.
```

Output:

```text
summary:
{'rows_read': 1, 'rows_written': 1, 'rows_failed': 0, 'spans_written': 2, 'warnings': []}

synthetic_output.csv:
patient_id,note_id,note_text
Patient/synthetic-csv-001,Note/synthetic-csv-001,Test MRN: 739518. Call 403-964-7364.
```

The same CSV workflow can be run from the CLI:

```bash
project-phi-deid synthetic_input.csv synthetic_output.csv \
  --audit-output-file synthetic_audit.csv
```

The CLI prints only summary counts and sanitized warnings. It does not accept
direct secret values on the command line; pass environment-variable names for
stable replacement modes.

More examples are in [docs/08_examples.md](docs/08_examples.md), including
bulk CSV processing, stable date shifting, stable patient-name surrogates,
stable provider-name surrogates, grouped unknown-name surrogates, custom regex
pass-through, and protected clinical terms.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 uv run python -m pytest -q tests
```

The tests use synthetic examples only and avoid asserting exact pyDeid
randomized surrogate values.
