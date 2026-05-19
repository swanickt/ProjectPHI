# Configuration

## `deidentify_note(...)`

```python
deidentify_note(
    note_text,
    *,
    patient_id=None,
    encounter_id=None,
    note_id=None,
    include_original_text=False,
    types=None,
    custom_dr_first_names=None,
    custom_dr_last_names=None,
    custom_patient_first_names=None,
    custom_patient_last_names=None,
    named_entity_recognition=False,
    stable_date_shift=False,
    date_shift_secret=None,
    date_shift_secret_env_var=None,
    date_shift_days=45,
    stable_patient_name_surrogates=False,
    patient_aliases=None,
    patient_name_secret=None,
    patient_name_secret_env_var=None,
    custom_regexes=None,
    protected_clinical_terms=None,
    include_builtin_protected_clinical_terms=True,
)
```

`named_entity_recognition=True` is rejected. The current project scope avoids NER and LLMs.

`include_original_text=True` returns the original note in memory as part of `DeidentificationResult`. Do not persist original text unless explicitly approved for the workflow.

## `deidentify_csv(...)`

```python
deidentify_csv(
    input_file,
    output_file,
    *,
    audit_output_file=None,
    note_text_column="note_text",
    patient_id_column="patient_id",
    encounter_id_column="encounter_id",
    note_id_column="note_id",
    types=None,
    custom_dr_first_names=None,
    custom_dr_last_names=None,
    custom_patient_first_names=None,
    custom_patient_last_names=None,
    encoding="utf-8",
    stable_date_shift=False,
    date_shift_secret=None,
    date_shift_secret_env_var=None,
    date_shift_days=45,
    stable_patient_name_surrogates=False,
    patient_aliases_by_patient_id=None,
    patient_name_secret=None,
    patient_name_secret_env_var=None,
    custom_regexes=None,
    protected_clinical_terms=None,
    include_builtin_protected_clinical_terms=True,
)
```

CSV processing preserves all input columns for successful rows and replaces only the note text column. Rows that fail are omitted from output and counted in the summary.

## Default Project Policy

The default behavior keeps pyDeid as the detector/pruner/replacement engine and
enables only the project semantic-preservation vetoes that do not require
secrets or patient-specific config:

- `stable_date_shift=False`: stable date shifting is off unless explicitly
  enabled.
- `stable_patient_name_surrogates=False`: stable patient-name replacement is
  off unless explicitly enabled with aliases and a secret.
- `include_builtin_protected_clinical_terms=True`: the small built-in protected
  clinical term set is active by default.
- Narrow semantic-preservation vetoes such as clinical abbreviation,
  obstetric-history shorthand, ordinary-token, title-token-fragment, and
  title-context action-word rules are available during project reconstruction.

Because built-in protected clinical terms are enabled by default, ProjectPHI
may reconstruct final text from original-note offsets even when stable dates
and stable patient-name surrogates are off. Reconstruction still uses only
pyDeid-emitted spans; it does not create a separate detector.

## `types`

`types` is passed to pyDeid. By default, the wrapper requests:

```python
[
    "names",
    "dates",
    "sin",
    "ohip",
    "mrn",
    "locations",
    "hospitals",
    "contact",
]
```

Stable date shifting requires `"dates"` when `types` is provided. Stable patient-name surrogates require `"names"` when `types` is provided.

## pyDeid Pass-Through Boundary

The public wrapper exposes only the pyDeid options that current project policy
uses directly:

- `types`;
- `custom_dr_first_names`;
- `custom_dr_last_names`;
- `custom_patient_first_names`;
- `custom_patient_last_names`;
- `named_entity_recognition`, which must remain `False`;
- pyDeid custom regex objects produced from `custom_regexes`.

The local pyDeid `deid_string(...)` also accepts date-year threshold options
such as `two_digit_threshold`, `valid_year_low`, and `valid_year_high`.
ProjectPHI currently leaves those at pyDeid defaults. 

## Stable Date Shifting

Parameters:

- `stable_date_shift=True`
- `patient_id`: required
- `date_shift_secret` or `date_shift_secret_env_var`: required
- `date_shift_days`: default `45`, meaning inclusive `[-45, +45]`

Recommended environment variable:

```bash
export PROJECT_PHI_DATE_SHIFT_SECRET="use-a-governed-runtime-secret"
```

Example:

```python
result = deidentify_note(
    "Follow-up on 2001-12-10.",
    patient_id="Patient/synthetic-001",
    stable_date_shift=True,
    date_shift_secret_env_var="PROJECT_PHI_DATE_SHIFT_SECRET",
)
```

Stable date shifting uses pyDeid-detected date spans only. It shifts ISO-style
full dates such as `2001-12-10`, common English month-name full dates such as
`March 14, 2026` or `8 August 2019`, and month/year spans such as
`March 2021` when pyDeid has already detected/pruned the span. These parsers
operate only inside those spans; they do not scan the full note or add new date
detections.

Month/year spans preserve month/year granularity. The implementation anchors
the source month internally to day 15, applies the same patient-specific day
offset used for full dates, and outputs only `Month YYYY`. For example,
`March 2021` may become `April 2021` if the stable offset crosses the month
boundary. It may remain `March 2021` if the stable offset stays within March.

Ambiguous or partial date-like text such as `March 14`, seasons, year-only
mentions, and times continues to follow the preservation or `<DATE>` fallback
policy.

ProjectPHI also preserves slash-form score/fraction notation when pyDeid has
emitted it as a date-like span and nearby clinical context supports a non-date
reading. This covers examples such as `CPAx 11/50`, `scored 1/50 points`,
staging/node-count text such as `N1 (1/61) M0`, and visual acuity such as
`6/60`. It also preserves bounded Apgar-style slash scores such as `4/7/10`
only when nearby context clearly indicates Apgar timing at 1, 5, and 10
minutes, and tumor-marker number fragments such as `CA 15-3` only in bounded
tumor-marker context. Bare slash dates such as `4/7/2010` continue to use
date-shift policy. The guard is span-local and does not scan the full note for
new dates or scores.

## Stable Patient-Name Surrogates

Parameters:

- `stable_patient_name_surrogates=True`
- `patient_id`: required
- `patient_aliases`: required for `deidentify_note(...)`
- `patient_aliases_by_patient_id`: required for `deidentify_csv(...)`
- `patient_name_secret` or `patient_name_secret_env_var`: required

Recommended environment variable:

```bash
export PROJECT_PHI_PATIENT_NAME_SECRET="use-a-governed-runtime-secret"
```

Example:

```python
result = deidentify_note(
    "Patient Zylanda Qorven attended.",
    patient_id="Patient/synthetic-002",
    stable_patient_name_surrogates=True,
    patient_aliases=["Zylanda Qorven", "Zylanda"],
    patient_name_secret_env_var="PROJECT_PHI_PATIENT_NAME_SECRET",
)
```

Only explicit aliases and conservative alias components are treated as the
patient. Matching aliases use one deterministic Faker-generated identity
seeded from patient_id and the patient-name secret. ProjectPHI prefers
Faker's Canadian English locale (en_CA), falls back to Faker's default locale
if needed, and uses the small in-source name pools only as an emergency
fallback. Unknown names remain pyDeid replacements.

The project does not infer gender from aliases, note text, pronouns, diagnosis,
or service line. Exact fake names may depend on the installed Faker
version/provider data, so pin the runtime environment if byte-for-byte stable
surrogate names are required across deployments.

### Behavior Without A Patient Alias Manifest

The pipeline does not infer patient aliases from note text. Clinical notes may
contain patient names, clinician names, family names, copied-correspondence
names, facilities, and organizations. Guessing aliases from note text could
incorrectly treat a non-patient name as the patient, which would damage role
semantics and over-replace text.

For governed CSV workflows, aliases should come from approved structured
registration or demographics data:

```text
structured patient table
  -> alias manifest: patient_id, alias
  -> deidentify_csv(..., stable_patient_name_surrogates=True)
```

If `stable_patient_name_surrogates=True` and no aliases are supplied for a row,
the row fails through the existing row-failure path. The failed row is omitted
from output, `rows_failed` increments, and summary/audit warnings are sanitized.

If stable patient-name surrogates are disabled, pyDeid still handles names with
its normal replacement behavior. Those replacements are not guaranteed to be
stable across consecutive notes for the same patient, so the same patient may
receive different pyDeid-generated replacements in different notes.

Stable date shifting is separate. It can remain stable across notes using
`patient_id` plus a date-shift secret, and it does not require a patient alias
manifest.

### Alias Manifest CSV

For CSV processing, aliases can be loaded from a small manifest with synthetic
or governed runtime data:

```csv
patient_id,alias
Patient/synthetic-002,Zylanda Qorven
Patient/synthetic-002,Zylanda
```

`load_patient_alias_manifest(path)` can be imported from
`project_phi.config_loaders` and returns:

```python
{"Patient/synthetic-002": ["Zylanda Qorven", "Zylanda"]}
```

The loader trims whitespace, preserves alias order per patient, skips completely
blank rows, and rejects missing columns or empty values with sanitized row-number
errors. It does not infer aliases or perform entity resolution.

## Custom Regexes

Custom regexes are configured as a dictionary keyed by project rule ID:

```python
custom_regexes = {
    "synthetic_accession": {
        "phi_type": "Synthetic Accession",
        "pattern": r"\bSYN-ACC-\d{4}\b",
        "replacement": "<SYNTHETIC_ACCESSION>",
    }
}
```

Required per rule:

- nonempty rule ID;
- nonempty `phi_type`;
- nonempty `pattern`.

Optional:

- `replacement`: string constant, defaulting to `<PHI>`.

The project converts this config into pyDeid custom regex objects. Project code does not scan note text directly with these patterns. Use synthetic examples in tests and documentation.

Custom regex config is also the current user-facing mechanism for governed
local facility, clinic, organization, department, accession, or identifier
patterns that pyDeid does not catch. Keep those rules in runtime config or an
internal artifact store rather than committing real site-specific lists to the
public repository. Use exact, narrow patterns first and record the rule ID in
audit output.

Synthetic facility-style example:

```json
{
  "synthetic_facility_name": {
    "phi_type": "Synthetic Facility",
    "pattern": "\\bNorthlake Regional Cancer Centre\\b",
    "replacement": "<SYNTHETIC_FACILITY>"
  }
}
```

Choose `phi_type` names carefully. Local pyDeid uses the configured `phi_type`
when selecting a surrogate, so custom types containing built-in pyDeid trigger
words such as `MRN`, `Name`, `Date`, `Time`, `Hospital`, `Telephone`, or
`Email` may use pyDeid's built-in replacement logic instead of the configured
constant `replacement`. If the intended final text is the configured constant,
use a neutral `phi_type`, for example `Synthetic Local Code`, and keep the
specific project meaning in the rule ID, audit metadata, or governed config
documentation.

The same dictionary can be loaded from JSON with
`load_custom_regexes_json(path)` from `project_phi.config_loaders`. The loader
performs shape validation and reuses the existing custom-regex validation path,
but it does not run regex matching over note text.

Example JSON:

```json
{
  "synthetic_accession": {
    "phi_type": "Synthetic Accession",
    "pattern": "\\bSYN-ACC-\\d{4}\\b",
    "replacement": "<SYNTHETIC_ACCESSION>"
  }
}
```

Validation errors do not echo raw regex patterns.

## Protected Clinical Terms

Protected clinical terms are semantic-preservation false-positive vetoes. They
operate only on `PHISpan` records emitted by pyDeid. They do not scan the full
note, detect PHI, create new spans, expand spans, use fuzzy matching, or use
NER/LLMs.

Parameters:

- `protected_clinical_terms`: optional runtime dictionary.
- `include_builtin_protected_clinical_terms`: default `True`.

Runtime dictionary shape:

```python
protected_clinical_terms = {
    "synthetic_breast_imaging": {
        "category": "breast_imaging_mammography",
        "terms": ["tomosynthesis", "mammography with tomosynthesis"],
    },
    "synthetic_clinical_tools": {
        "category": "clinical_tools_scales_criteria",
        "terms": ["JOA score", "Fazekas grade"],
        "component_terms": [
            {
                "component": "Chelsea",
                "within_phrase": "Chelsea Critical Care Physical Assessment Tool",
            }
        ],
    }
}
```

Matching is exact after simple normalization: trim surrounding whitespace,
casefold, collapse internal whitespace, and strip clearly surrounding
punctuation. There is no substring matching. If pyDeid emits a span whose whole
normalized text exactly matches a protected term, the project preserves the
span text and records `replacement_source="project_protected_clinical_term"`.
For selected high-risk eponym components, such as `Chelsea`, preservation can
also require exact local phrase context, such as `Chelsea Critical Care
Physical Assessment Tool`. This remains span-local around a pyDeid-emitted
span; it is not a full-note scan and does not create new spans.

The built-in set is manually curated, general, and non-site-specific. It covers
selected breast imaging, mammography, breast cancer pathology,
receptor/biomarker status, staging, recurrence/metastasis, systemic/endocrine
therapy, radiology/imaging, treatment, surgery/radiation, and
remission/disease-status terms. It also includes selected clinical
tools/scales/criteria as full phrases or context-bound components where local
evaluation showed semantic damage. Examples include `tomosynthesis`,
`bilateral digital mammography with tomosynthesis`, `ER+/PR+/HER2-`,
`cT2N1M0`, `ductal carcinoma in situ`, `metastatic disease`, `DEXA scan`,
`dose-dense AC-T`, `letrozole`, `clinical and radiographic remission`,
`ECOG performance status`, `Karnofsky Performance Status`, `RECIST 1.1`,
`CTCAE grade`, `JOA score`, `Fazekas grade`, and `Chelsea Critical Care
Physical Assessment Tool`.
It is not a bulk export from NCIt, RadLex, SNOMED CT, UMLS, pyDeid wordlists,
or any other external terminology source.

This behavior intentionally prioritizes semantic preservation for internal
training candidate generation. It carries residual risk: a rare person,
facility, or organization name could match a protected clinical term. It is not
a legal/compliance guarantee and does not make output safe for external
release. Real governed use requires institutional, legal, and governance review.

### Protected Clinical Terms CSV

Additional runtime terms can be loaded from CSV. The simplest form protects
whole pyDeid spans:

```csv
rule_id,category,term
synthetic_breast_imaging,breast_imaging,tomosynthesis
synthetic_breast_imaging,breast_imaging,mammography with tomosynthesis
```

For risky components that are also plausible names or places, use
`component,within_phrase` columns instead of protecting the component globally:

```csv
rule_id,category,term,component,within_phrase
synthetic_tools,clinical_tools,,Chelsea,Chelsea Critical Care Physical Assessment Tool
synthetic_tools,clinical_tools,JOA score,,
```

`load_protected_clinical_terms_csv(path)` can be imported from
`project_phi.config_loaders`. The loader skips blank rows, preserves rule/term
order, rejects missing columns, empty values, or incomplete component rows with
sanitized row-number errors, and does not infer terms.

Larger externally derived protected-term lists should be managed as governed
runtime CSV artifacts and supplied with `--protected-clinical-terms-csv`. Do
not commit large terminology-derived lists to the public repository.

Source guidance:

- NCIt is suitable for oncology and breast cancer terminology, subject to
  attribution and license handling.
- RadLex is suitable for radiology and mammography terminology, subject to RSNA
  license and attribution handling.
- SNOMED CT and UMLS-derived lists should remain governed internal artifacts
  unless redistribution rights are explicitly cleared.

Keep source/version/license metadata in a sidecar file beside governed CSVs.
Recommended fields:

```json
{
  "artifact_version": "synthetic-2026-05-16",
  "review_status": "reviewed",
  "governance_owner": "approved curator role",
  "approval_review_date": "2026-05-16",
  "sources": [
    {
      "source_name": "Synthetic terminology source",
      "source_version": "example",
      "source_release_date": "2026-05-01",
      "source_url": "https://example.invalid/synthetic-source",
      "source_license": "example license",
      "extraction_date": "2026-05-16",
      "extraction_method": "documented exact-term extraction and manual review"
    }
  ]
}
```

The sidecar is for governance and attribution. The current runtime CSV loader
expects data rows with `rule_id,category,term` for whole-span terms, or
`rule_id,category,component,within_phrase` for context-bound components. It
does not parse sidecar metadata.

## CLI

Run CSV de-identification through:

```bash
python -m project_phi.cli synthetic_input.csv synthetic_output.csv
```

If installed with the console script, the equivalent command is:

```bash
project-phi-deid synthetic_input.csv synthetic_output.csv
```

Common options:

```bash
project-phi-deid synthetic_input.csv synthetic_output.csv \
  --audit-output-file synthetic_audit.csv \
  --stable-date-shift \
  --date-shift-secret-env-var PROJECT_PHI_DATE_SHIFT_SECRET \
  --stable-patient-name-surrogates \
  --patient-alias-manifest synthetic_aliases.csv \
  --patient-name-secret-env-var PROJECT_PHI_PATIENT_NAME_SECRET \
  --custom-regex-json synthetic_regexes.json \
  --protected-clinical-terms-csv synthetic_protected_terms.csv
```

The CLI accepts secret environment-variable names only, not direct secret
values. It prints summary counts and sanitized warnings; it does not print raw
note text, aliases, regex patterns, detected PHI, secrets, hashes, or HMAC
digests.

## Audit Output

Set `audit_output_file` on `deidentify_csv(...)` to emit audit rows:

```python
summary = deidentify_csv(
    "synthetic_input.csv",
    "synthetic_output.csv",
    audit_output_file="synthetic_audit.csv",
)
```

Audit CSVs are internal artifacts and may include replacement metadata, exact
offsets, protected-term policy metadata, title-token-fragment metadata, and
title-context action-word policy metadata. They should not be used as training
outputs.

For detailed synthetic input/output examples covering single-note behavior,
CSV row failures, stable replacement, protected terms, and custom regexes, see
[Examples](09_examples.md).

## Installation Notes

ProjectPHI's recommended local setup uses `uv`. Install `uv` first if it is
not already available:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then create a Python 3.11 environment and install the project editable with its
development test dependency:

```bash
uv venv .venv --python 3.11
source .venv/bin/activate
uv sync --extra dev
```

The `pyproject.toml` dependency list pins pyDeid to a specific GitHub commit,
and `uv.lock` records the resolved package set. The dependency list includes
compatibility constraints for pyDeid's current dependency stack:

- `setuptools<81`, because pyDeid imports `pkg_resources`;
- `numpy<2`, because pyDeid's spaCy/thinc stack is not compatible with newer
  NumPy releases in the tested environment.

The first install needs internet access for GitHub and the configured package
index. Returning to an already-created `.venv` does not need internet for
normal local execution.

