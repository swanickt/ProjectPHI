# ProjectPHI

**ProjectPHI** is a [pyDeid](https://github.com/GEMINI-Medicine/pyDeid)-based clinical free-text de-identification
wrapper. It is intended to reduce identifier
risk while preserving clinically useful text for downstream review and possible use in machine-learning training.

It is not a legal certification tool. It does not guarantee full text de-identification,
anonymization, PHIPA compliance, HIPAA compliance, or external-release safety.

## Documentation

Start with [docs/00_index.md](docs/00_index.md).

Key pages:

- [Pipeline overview](docs/01_pipeline_overview.md)
- [Architecture](docs/02_architecture.md)
- [pyDeid behavior used by ProjectPHI](docs/03_pydeid_behavior.md)
- [ProjectPHI behavior](docs/04_ProjectPHI_behavior.md)
- [Configuration](docs/05_configuration.md)
- [Privacy and audit notes](docs/06_privacy_and_audit_notes.md)
- [Semantic preservation](docs/07_semantic_preservation.md)
- [Developer notes](docs/08_developer_notes.md)
- [Examples](docs/09_examples.md)

## Current Capabilities

- Single-note de-identification through `deidentify_note(...)`.
- Batch de-identification through `deidentify_csv(...)`.
- pyDeid-first PHI detection, pruning, and initial surrogate replacement.
- Stable per-patient date shifting for pyDeid-detected ISO-style full dates,
  common English month-name full dates, and month/year spans.
- Stable patient-name surrogates for explicit patient aliases that pyDeid
  detects, generated deterministically from `patient_id` and a runtime secret.
- Protected clinical terminology false-positive vetoes for curated pyDeid
  false positives, with built-in general breast/oncology/radiology terms.
- Minimal custom regex pass-through to pyDeid using configured patterns.
- Optional internal audit CSV output that records span metadata without raw
  detected PHI text.
- Config loaders and a minimal CSV CLI.

## What ProjectPHI Does Not Do

- It does not use NER or LLMs.
- It does not call external APIs.
- It does not add a separate PHI detector.
- It does not add Sunnybrook/Ontario site-specific regexes (yet).
- It does not bundle pyDeid inside the `project_phi` package.
- It does not commit large external terminology-derived protected-term lists.
- It does not directly copy, mine, transform, or redistribute pyDeid wordlists
  such as `sno_edited.txt`.
- It does not guarantee that every sensitive phrase is removed.
- It does not claim to make outputs safe for external release by itself.

## Installation

Clone the repository first:

```bash
git clone <repo-url>
cd ProjectPHI
```

ProjectPHI uses `uv` for environment management. If `uv` is not
installed, install it first:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Then create a Python 3.11 virtual environment and install ProjectPHI editable
with its development test dependency:

```bash
uv venv .venv --python 3.11
source .venv/bin/activate
uv sync --extra dev
```

The first sync needs internet access because `uv` fetches pyDeid from the
pinned GitHub commit in `pyproject.toml` / `uv.lock` and resolves Python
dependencies from the configured package index. After the environment has been
created, normal local runs do not need internet unless the environment is
rebuilt or dependency pins change.

pyDeid is an external dependency. ProjectPHI does not bundle pyDeid inside the
`project_phi` package. The current pinned pyDeid stack requires compatibility
constraints declared in `pyproject.toml`, including `setuptools<81` for
pyDeid's `pkg_resources` import and `numpy<2` for spaCy/thinc compatibility.

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
surrogate offsets and project-final replacement offsets are stored separately
in span metadata. pyDeid surrogate records are the table-like PHI records
returned by pyDeid for detected spans; they are normalized into `PHISpan`
objects and are separate from CSV input rows.

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

Observed using a synthetic one-row CSV:

```text
synthetic_input.csv:
patient_id,note_id,note_text
Patient/synthetic-csv-001,Note/synthetic-csv-001,Test MRN: 011-0111. Call 416-555-1212.

summary:
{'rows_read': 1, 'rows_written': 1, 'rows_failed': 0, 'spans_written': 2, 'warnings': []}

synthetic_output.csv:
patient_id,note_id,note_text
Patient/synthetic-csv-001,Note/synthetic-csv-001,Test MRN: 1672469. Call 807-792-7136.

final de-identified note_text:
Test MRN: 1672469. Call 807-792-7136.

synthetic_audit.csv header:
patient_id,encounter_id,note_id,span_index,start,end,label,source,action,pydeid_types,warning,replacement_source,project_replacement,project_replacement_start,project_replacement_end,pydeid_replacement,pydeid_surrogate_start,pydeid_surrogate_end,project_date_shift_days,project_date_shift_range_days,project_date_shift_policy,project_name_policy,name_role,alias_match_type,custom_regex_rule_id,custom_regex_phi_type,project_protected_term_policy,project_protected_term_rule_id,project_protected_term_category
```

The same CSV workflow can be run from the CLI:

```bash
project-phi-deid synthetic_input.csv synthetic_output.csv \
  --audit-output-file synthetic_audit.csv
```

The CLI prints only summary counts and sanitized warnings. It does not accept
direct secret values on the command line; pass environment-variable names for
stable replacement modes.

### Bulk CSV Example With Stable Dates And Patient Names

This synthetic bulk example uses five CSV rows. Two rows belong to the same
patient, which shows that stable date shifting preserves the interval between
their dates and that explicit patient aliases map to the same fake identity.

```text
synthetic_aliases.csv:
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

synthetic_input.csv:
patient_id,note_id,note_text
Patient/bulk-001,Note/bulk-001-a,"Patient Zylanda Qorven seen on March 14, 2026. Call 416-555-0101."
Patient/bulk-001,Note/bulk-001-b,"Zylanda returned on March 21, 2026. Continue letrozole."
Patient/bulk-002,Note/bulk-002-a,"Patient Maribel Voss had CT on April 1, 2026. MRN SYN-2222."
Patient/bulk-003,Note/bulk-003-a,"Dr. Theo Calder reviewed mammography with tomosynthesis on May 5, 2026."
Patient/bulk-004,Note/bulk-004-a,Follow-up booked for June 2026 after remission visit.
```

Output:

```text
summary:
{'rows_read': 5, 'rows_written': 5, 'rows_failed': 0, 'spans_written': 13, 'warnings': []}

synthetic_output.csv:
patient_id,note_id,note_text
Patient/bulk-001,Note/bulk-001-a,"Patient Spencer Thompson seen on March 27, 2026. Call 416-572-1264."
Patient/bulk-001,Note/bulk-001-b,"Spencer returned on April 3, 2026. Continue letrozole."
Patient/bulk-002,Note/bulk-002-a,"Patient Barry Walker had CT on February 17, 2026. MRN SYN-2222."
Patient/bulk-003,Note/bulk-003-a,"Dr. Steven Stout reviewed mammography with tomosynthesis on May 10, 2026."
Patient/bulk-004,Note/bulk-004-a,Follow-up booked for May 2026 after remission visit.
```

In the first two rows, the same patient gets the same fake given name
(`Spencer`) and the two dates are shifted by the same patient-specific offset
from seven days apart to seven days apart. The clinical phrase `mammography
with tomosynthesis` is preserved by the protected clinical term policy.

The value `SYN-2222` remains in the first run because pyDeid did not detect
that synthetic format as an identifier and no custom regex was configured for
it. If a similar pattern represented a governed local/site-specific identifier,
that is the kind of concrete gap to address with a pyDeid custom regex:

```json
{
  "synthetic_local_code": {
    "phi_type": "Synthetic Local Code",
    "pattern": "\\bSYN-\\d{4}\\b",
    "replacement": "<SYNTHETIC_LOCAL_CODE>"
  }
}
```

With that custom regex passed to the same bulk run, the relevant output row
becomes:

```text
summary:
{'rows_read': 5, 'rows_written': 5, 'rows_failed': 0, 'spans_written': 14, 'warnings': []}

synthetic_output.csv row:
Patient/bulk-002,Note/bulk-002-a,"Patient Barry Walker had CT on February 17, 2026. MRN <SYNTHETIC_LOCAL_CODE>."

custom regex audit metadata:
custom_regex_rule_id=synthetic_local_code
custom_regex_phi_type=Synthetic Local Code
```

The configured `phi_type` is intentionally neutral. pyDeid uses `phi_type`
when choosing replacement behavior, so names containing built-in pyDeid type
words such as `MRN`, `Name`, `Date`, `Time`, or `Hospital` can trigger pyDeid's
built-in surrogate generators before the custom replacement is used. Use a
neutral PHI type when the intended final text is the configured constant
replacement. ProjectPHI records the custom rule ID and PHI type in audit
metadata without including the raw regex pattern.


## Stable Replacement Examples

Stable date shifting:

```python
result = deidentify_note(
    "Follow-up on March 14, 2026 after diagnosis in March 2021.",
    patient_id="Patient/synthetic-date-001",
    stable_date_shift=True,
    date_shift_secret_env_var="PROJECT_PHI_DATE_SHIFT_SECRET",
)
```

Output:

```text
deidentified_text:
Follow-up on March 29, 2026 after diagnosis in March 2021.

spans:
DATE March 14, 2026 -> March 29, 2026
replacement_source=project_stable_date_shift
project_date_shift_policy=shifted_natural_language_full_date

DATE March 2021 -> March 2021
replacement_source=project_stable_date_shift
project_date_shift_policy=shifted_month_year
```

Full dates keep day/month/year granularity. Month/year spans keep month/year
granularity by using the same patient-specific day offset with an internal
day-15 anchor, for example `March 2021 -> April 2021` when the patient's stable
offset crosses the month boundary.

Stable patient-name surrogates require explicit aliases:

```python
result = deidentify_note(
    "Patient Zylanda Qorven attended.",
    patient_id="Patient/synthetic-name-001",
    stable_patient_name_surrogates=True,
    patient_aliases=["Zylanda Qorven"],
    patient_name_secret_env_var="PROJECT_PHI_PATIENT_NAME_SECRET",
)
```

Output:

```text
deidentified_text:
Patient Brooke Hernandez attended.

spans:
NAME Zylanda -> Brooke
replacement_source=project_stable_patient_name
alias_match_type=given

NAME Qorven -> Hernandez
replacement_source=project_stable_patient_name
alias_match_type=family
```

For CSV stable patient-name surrogates, provide an alias manifest generated
from approved structured registration/demographics data, not by scraping note
text:

```csv
patient_id,alias
Patient/synthetic-name-001,Zylanda Qorven
Patient/synthetic-name-001,Zylanda
```

Example `synthetic_input.csv`:

```csv
patient_id,note_text
Patient/synthetic-name-001,Patient Zylanda Qorven attended.
```

```bash
project-phi-deid synthetic_input.csv synthetic_output.csv \
  --stable-patient-name-surrogates \
  --patient-alias-manifest synthetic_aliases.csv \
  --patient-name-secret-env-var PROJECT_PHI_PATIENT_NAME_SECRET
```

Output:

```text
synthetic_aliases.csv:
patient_id,alias
Patient/synthetic-name-001,Zylanda Qorven
Patient/synthetic-name-001,Zylanda

synthetic_input.csv:
patient_id,note_text
Patient/synthetic-name-001,Patient Zylanda Qorven attended.

CLI summary:
rows_read=1
rows_written=1
rows_failed=0
spans_written=2
warnings=0

synthetic_output.csv:
patient_id,note_text
Patient/synthetic-name-001,Patient Brooke Hernandez attended.

final de-identified note_text:
Patient Brooke Hernandez attended.
```

## Custom Regex And Protected Terms

Custom regexes are passed through to pyDeid. Project code does not run them as a
separate detector:

```json
{
  "synthetic_accession": {
    "phi_type": "Synthetic Accession",
    "pattern": "\\bSYN-ACC-\\d{4}\\b",
    "replacement": "<SYNTHETIC_ACCESSION>"
  }
}
```

Example `synthetic_input.csv`:

```csv
patient_id,note_text
Patient/synthetic-regex-001,Synthetic accession SYN-ACC-1234 reviewed.
```

```bash
project-phi-deid synthetic_input.csv synthetic_output.csv \
  --custom-regex-json synthetic_regexes.json
```

Observed CLI summary and synthetic output from the current test environment:

```text
synthetic_regexes.json:
{
  "synthetic_accession": {
    "phi_type": "Synthetic Accession",
    "pattern": "\\bSYN-ACC-\\d{4}\\b",
    "replacement": "<SYNTHETIC_ACCESSION>"
  }
}

synthetic_input.csv:
patient_id,note_text
Patient/synthetic-regex-001,Synthetic accession SYN-ACC-1234 reviewed.

CLI summary:
rows_read=1
rows_written=1
rows_failed=0
spans_written=1
warnings=0

synthetic_output.csv:
patient_id,note_text
Patient/synthetic-regex-001,Synthetic accession <SYNTHETIC_ACCESSION> reviewed.

final de-identified note_text:
Synthetic accession <SYNTHETIC_ACCESSION> reviewed.

custom_regex_rule_id=synthetic_accession
custom_regex_phi_type=Synthetic Accession
pydeid_replacement=<SYNTHETIC_ACCESSION>
```

Protected clinical terms are span-local false-positive vetoes for pyDeid spans.
The built-in protected clinical term set is enabled by default. Larger
terminology-derived lists should be governed runtime CSV artifacts, not
committed to the public repository.

Example CLI summary and synthetic output,
using the built-in `tomosynthesis` protection:

```text
synthetic_input.csv:
patient_id,note_text
Patient/synthetic-protected-001,Dr. Tomosynthesis saw the patient.

CLI summary:
rows_read=1
rows_written=1
rows_failed=0
spans_written=1
warnings=0

synthetic_output.csv:
patient_id,note_text
Patient/synthetic-protected-001,Dr. Tomosynthesis saw the patient.

final de-identified note_text:
Dr. Tomosynthesis saw the patient.

replacement_source=project_protected_clinical_term
project_protected_term_rule_id=breast_imaging_mammography
project_replacement=Tomosynthesis
```

See [Semantic Preservation](docs/07_semantic_preservation.md) for the external
terminology-source policy.

## Audit CSV Warning

Audit CSVs are internal audit artifacts. They may include fake replacements,
shifted date values, exact project replacement offsets, date-shift offsets,
labels, and policy metadata. They are not training outputs.

Audit replacement metadata is explicit: project-final values use
`project_replacement*` columns, and pyDeid's initial replacement view uses
`pydeid_replacement` / `pydeid_surrogate_*` columns.

Audit output does not include raw note text, raw detected PHI text, raw regex
patterns, secrets, raw HMAC digests, hashes, or raw alias lists.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 uv run python -m pytest -q tests
```

The tests use synthetic examples only. They intentionally avoid asserting exact
pyDeid randomized surrogate values.
