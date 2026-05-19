# ProjectPHI

**ProjectPHI** is a [pyDeid](https://github.com/GEMINI-Medicine/pyDeid)-based clinical free-text de-identification
wrapper. It is intended to reduce identifier
risk while preserving clinically useful text for downstream review and possible use in machine-learning training.

It is not a legal certification tool. It does not guarantee full text de-identification,
anonymization, PHIPA compliance, HIPAA compliance, or external-release safety.

## Documentation (NOTE: These doc files are currently a local work in progress)

Start with [docs/00_index.md](docs/00_index.md).

Key pages:

- [Pipeline overview](docs/01_pipeline_overview.md)
- [Architecture](docs/02_architecture.md)
- [pyDeid behavior](docs/03_pydeid_behavior.md)
- [ProjectPHI behavior](docs/04_ProjectPHI_behavior.md)
- [Configuration](docs/05_configuration.md)
- [Privacy and audit notes](docs/06_privacy_and_audit_notes.md)
- [Semantic preservation](docs/07_semantic_preservation.md)
- [Examples](docs/09_examples.md)
- [Current limitations](docs/10_current_limitations.md)

## Current Capabilities

- Single-note de-identification with `deidentify_note(...)`.
- Batch/CSV de-identification with `deidentify_csv(...)` and `project-phi-deid`.
- pyDeid-first PHI detection, pruning, custom regex matching, custom name-list
  handling, and initial surrogate generation.
- Normalized `PHISpan` records with original-note offsets, pyDeid surrogate
  metadata, and project-final replacement metadata kept separate.
- Stable per-patient date shifting for pyDeid-detected parseable full dates and
  month/year spans.
- Stable patient-name surrogates for explicit patient aliases that pyDeid
  detects, generated deterministically from `patient_id` and a runtime secret.
- Runtime config loaders for patient alias manifests, custom regex JSON, and
  protected clinical terms CSV.
- Internal audit CSV output for span-level review.
- Minimal CSV CLI.

## What ProjectPHI Does Not Do

- It does not use NER, LLMs, external APIs, or a separate PHI detector (outside PyDeid).
- It does not ship Sunnybrook/Ontario site-specific regexes, facility lists,
  provider lists, or broad gazetteers (yet).
- It does not bundle pyDeid inside the `project_phi` package.
- It does not commit large external terminology-derived protected-term lists.
- It does not guarantee that every sensitive phrase is removed.
- It does not claim to make outputs safe for external release by itself.

## Installation

Clone the repository first:

```
git clone <repo-url>
cd ProjectPHI
```

ProjectPHI uses `uv` for environment management. If `uv` is not
installed, install it first:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Create a Python 3.11 environment and install the project:

```
uv venv .venv --python 3.11
source .venv/bin/activate
uv sync --extra dev
```

The first sync needs internet access because `uv` fetches pyDeid from the
pinned GitHub commit in `pyproject.toml` / `uv.lock` and resolves Python
dependencies from the configured package index. After the environment has been
created, normal local runs do not need internet unless the environment is
rebuilt or dependency pins change.

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

Output:

```text
deidentified_text:
Test MRN: 6534324. Follow-up on 2001-11-20.

spans:
ID 10 18 ['MRN'] 6534324
pyDeid
pydeid_replacement
DATE 33 43 ['Year/Month/Day [yy(yy)/mm/dd]'] 2001-11-20
project_stable_date_shift
shifted_full_date
```
`PHISpan.start` and `PHISpan.end` are offsets into the original note. pyDeid
surrogate offsets and project-final replacement offsets live in separate span
metadata fields.

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

## Bulk CSV Example

This synthetic example has five rows. Two rows share the same patient ID, which
shows stable date shifting and stable patient-name replacement across notes.

```csv
patient_id,note_id,note_text
Patient/bulk-001,Note/bulk-001-a,"Patient Zylanda Qorven seen on March 14, 2026. Call 416-555-0101."
Patient/bulk-001,Note/bulk-001-b,"Zylanda returned on March 21, 2026. Continue letrozole."
Patient/bulk-002,Note/bulk-002-a,"Patient Maribel Voss had CT on April 1, 2026. MRN SYN-2222."
Patient/bulk-003,Note/bulk-003-a,"Imaging reviewed mammography with tomosynthesis on May 5, 2026."
Patient/bulk-004,Note/bulk-004-a,Follow-up booked for June 2026 after remission visit.
```

With this alias manifest

```csv
patient_id,alias
Patient/bulk-001,Zylanda Qorven
Patient/bulk-001,Zylanda
Patient/bulk-002,Maribel Voss
Patient/bulk-002,Maribel
Patient/bulk-002,Voss
Patient/bulk-003,Lumina Frost
Patient/bulk-003,Lumina
Patient/bulk-003,Frost
Patient/bulk-004,Orion Vale
Patient/bulk-004,Orion
Patient/bulk-004,Vale
```

Observed output with stable dates and stable patient-name surrogates:

```csv
patient_id,note_id,note_text
Patient/bulk-001,Note/bulk-001-a,"Patient Spencer Thompson seen on March 27, 2026. Call 867-856-4595."
Patient/bulk-001,Note/bulk-001-b,"Spencer returned on April 3, 2026. Continue letrozole."
Patient/bulk-002,Note/bulk-002-a,"Patient Barry Walker had CT on February 17, 2026. MRN SYN-2222."
Patient/bulk-003,Note/bulk-003-a,"Imaging reviewed mammography with tomosynthesis on May 10, 2026."
Patient/bulk-004,Note/bulk-004-a,Follow-up booked for May 2026 after remission visit.
```

`SYN-2222` remains because pyDeid did not detect that synthetic format and no
custom regex was configured. If a similar governed local pattern represented a
real identifier family, configure a pyDeid custom regex at runtime:

```json
{
  "synthetic_local_code": {
    "phi_type": "Synthetic Local Code",
    "pattern": "\\bSYN-\\d{4}\\b",
    "replacement": "<SYNTHETIC_LOCAL_CODE>"
  }
}
```

Observed output for that row after passing the custom regex:

```csv
Patient/bulk-002,Note/bulk-002-a,"Patient Barry Walker had CT on February 17, 2026. MRN <SYNTHETIC_LOCAL_CODE>."
```

Custom regexes are passed through to pyDeid. ProjectPHI does not run the regex
over the note text as a separate detector.

## Stable Date Example

```python
result = deidentify_note(
    "Follow-up on March 14, 2026 after diagnosis in March 2021.",
    patient_id="Patient/synthetic-date-001",
    stable_date_shift=True,
    date_shift_secret="synthetic-demo-secret",
)
```

Observed output:

```text
Follow-up on February 5, 2026 after diagnosis in February 2021.

DATE March 14, 2026 -> February 5, 2026
replacement_source=project_stable_date_shift
project_date_shift_policy=shifted_natural_language_full_date

DATE March 2021 -> February 2021
replacement_source=project_stable_date_shift
project_date_shift_policy=shifted_month_year
```

Full dates keep day/month/year granularity. Month/year spans keep month/year
granularity by using the same patient-specific day offset with an internal
day-15 anchor.

## Stable Patient-Name Example

```python
result = deidentify_note(
    "Patient Zylanda Qorven attended.",
    patient_id="Patient/synthetic-name-001",
    stable_patient_name_surrogates=True,
    patient_aliases=["Zylanda Qorven", "Zylanda"],
    patient_name_secret="synthetic-name-secret",
)
```

Observed output:

```text
Patient Brooke Hernandez attended.

NAME Zylanda -> Brooke
replacement_source=project_stable_patient_name
alias_match_type=given

NAME Qorven -> Hernandez
replacement_source=project_stable_patient_name
alias_match_type=family
```

Stable patient-name surrogates require explicit aliases. The wrapper does not infer
patient aliases from note text. Stable fake patient identities prefer Faker's
Canadian English locale (en_CA) and are keyed by patient_id plus a runtime
secret.

## Protected Clinical Terms

Protected clinical terms are span-local false-positive vetoes. They operate
only on pyDeid-emitted spans. They do not detect new PHI and do not scan the
full note.

For example, current pyDeid may leave this sentence unchanged without emitting
any PHI span:

```text
Mammography with tomosynthesis showed no suspicious mass.
```

ProjectPHI does not need to intervene in that case. If pyDeid does emit a span
whose whole normalized text exactly matches a built-in or runtime protected
clinical term, ProjectPHI preserves the original clinical term and records
`replacement_source="project_protected_clinical_term"` in metadata.

The built-in protected term set is enabled by default, manually curated,
general, and non-site-specific. Treat this as the stable baseline. Further
terminology improvements should come from governed local evaluation or runtime
protected-term CSVs, not broad built-in expansion.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 uv run python -m pytest -q tests
```

The tests use synthetic examples only and avoid asserting exact pyDeid
randomized surrogate values.

