# Examples

These examples are synthetic. They show expected behavior and
metadata shape, not exact pyDeid randomized replacements. pyDeid may choose
different surrogate names, facilities, or IDs across runs.

## Single Note With Raw pyDeid Output Preserved

Input:

```text
Patient Joe Horton was seen by Dr. Arlen Pavo on 2001-12-10.
Call 416-555-0101 for follow-up.
```

Configuration:

```text
deidentify_note(...)
stable_date_shift=False
stable_patient_name_surrogates=False
```

Expected behavior:

- pyDeid detects and prunes PHI spans.
- ProjectPHI normalizes pyDeid surrogate records into `PHISpan` objects.
- Because no project reconstruction policy is enabled, `deidentified_text` is
  pyDeid's de-identified string.
- Each `PHISpan.start` and `PHISpan.end` points into the original note.
- pyDeid surrogate offsets remain in span metadata as
  `pydeid_surrogate_start` and `pydeid_surrogate_end`.

Example output shape:

```text
Patient <pyDeid-name-surrogate> was seen by Dr. <pyDeid-name-surrogate> on <pyDeid-date-surrogate>.
Call <pyDeid-phone-surrogate> for follow-up.
```

The exact surrogate values are pyDeid behavior and should not be used as stable
test assertions.

## Stable Date Shifting

Input:

```text
Follow-up on March 14, 2026 after diagnosis in March 2021.
Repeat imaging on April 1, 2026.
```

Configuration:

```text
patient_id="Patient/synthetic-001"
stable_date_shift=True
date_shift_secret_env_var="PROJECT_PHI_DATE_SHIFT_SECRET"
```

Expected behavior:

- pyDeid must first emit date spans for the dates.
- Full dates such as `March 14, 2026` and `April 1, 2026` are shifted by the
  same patient-specific HMAC-derived day offset.
- The interval between shifted full dates is preserved.
- Month/year spans such as `March 2021` use the same patient-specific day
  offset with an internal day-15 anchor and output only `Month YYYY`.
- Year-only mentions, times, seasons, and holidays are preserved by default.
- The HMAC digest and secret are not returned, logged, or written to audit.

Example output shape:

```text
Follow-up on <shifted month-name full date> after diagnosis in <shifted month/year>.
Repeat imaging on <shifted month-name full date>.
```

Relevant span metadata:

```text
replacement_source="project_stable_date_shift"
project_replacement="<shifted date text>"
project_replacement_start=<offset in final text>
project_replacement_end=<offset in final text>
project_date_shift_days=<patient-specific integer offset>
project_date_shift_range_days=45
project_date_shift_policy="shifted_full_date" or "shifted_month_year"
pydeid_replacement="<pyDeid randomized date replacement>"
pydeid_surrogate_start=<offset in pyDeid text>
pydeid_surrogate_end=<offset in pyDeid text>
```

## Stable Patient-Name Surrogates

Input:

```text
Patient Zylanda Qorven attended with Dr. Arlen Pavo.
Zylanda reports improved appetite.
```

Configuration:

```text
patient_id="Patient/synthetic-002"
stable_patient_name_surrogates=True
patient_aliases=["Zylanda Qorven", "Zylanda"]
patient_name_secret_env_var="PROJECT_PHI_PATIENT_NAME_SECRET"
custom_dr_first_names={"Arlen"}
custom_dr_last_names={"Pavo"}
```

Expected behavior:

- pyDeid remains responsible for detecting general name spans.
- Patient aliases are not inferred from note text.
- pyDeid-detected spans matching explicit patient aliases use one deterministic
  Faker-generated patient identity for the same `patient_id`, secret, and
  pinned runtime environment.
- Supplied aliases that pyDeid misses or prunes can still be replaced by a
  bounded exact residual pass.
- Unknown or clinician names remain pyDeid replacements in single-note/CSV
  workflows and are not treated as patient aliases.

Example output shape:

```text
Patient <stable fake patient full name> attended with Dr. <pyDeid-name-surrogate>.
<stable fake patient given name> reports improved appetite.
```

Relevant known-patient span metadata:

```text
replacement_source="project_stable_patient_name"
project_name_policy="known_patient_alias"
name_role="known_patient_alias"
alias_match_type="full" or "given"
```

If pyDeid prunes a supplied alias before ProjectPHI sees it, the residual span
uses:

```text
replacement_source="project_residual_patient_alias"
project_name_policy="residual_explicit_patient_alias"
name_role="known_patient_alias"
alias_match_type="full" or "given" or "family" or "title_family"
```

Relevant unknown-name span metadata, when reconstruction metadata is present:

```text
project_name_policy="unknown_name_pydeid"
name_role="unknown_name"
```

## Patient Timeline Unknown-Name Surrogates

Input notes for one patient:

```text
n1: Maria Lopez called the clinic.
n2: Maria called again.
n3: Lopez left a message.
```

Configuration:

```python
from project_phi import deidentify_patient_notes

batch = deidentify_patient_notes(
    [
        {"note_id": "n1", "note_text": "Maria Lopez called the clinic."},
        {"note_id": "n2", "note_text": "Maria called again."},
        {"note_id": "n3", "note_text": "Lopez left a message."},
    ],
    patient_id="Patient/synthetic-003",
    stable_unknown_name_surrogates=True,
    unknown_name_secret_env_var="PROJECT_PHI_UNKNOWN_NAME_SECRET",
)
```

Expected behavior:

- pyDeid remains responsible for detecting the name spans.
- The registry is built only within this one patient's supplied notes.
- `Maria Lopez` receives one deterministic fake full name.
- Later standalone `Maria` and `Lopez` link to that fake given/family name only
  because each component is unique in the batch.
- If `Maria Lopez` and `Maria Santos` both occur, standalone `Maria` receives a
  separate stable standalone surrogate instead of linking arbitrarily.

Relevant span metadata:

```text
replacement_source="project_stable_unknown_name"
project_name_policy="stable_unknown_name_within_patient"
name_role="unknown_name"
alias_match_type="full" or "linked_given" or "linked_family" or "standalone"
```

CSV/CLI grouped mode:

```python
summary = deidentify_csv(
    "input.csv",
    "output.csv",
    stable_unknown_name_surrogates=True,
    unknown_name_secret_env_var="PROJECT_PHI_UNKNOWN_NAME_SECRET",
)
```

```bash
project-phi-deid input.csv output.csv \
  --stable-unknown-name-surrogates \
  --unknown-name-secret-env-var PROJECT_PHI_UNKNOWN_NAME_SECRET
```

CSV/CLI grouping uses `patient_id_column`, processes each patient's rows as one
batch, and writes successful rows back in original input order. Missing patient
IDs fail through sanitized row-failure handling.

## Stable Provider-Name Surrogates

Input:

```text
Radiologist Chen reviewed mammography.
Copy to Lena Shore after review.
Green vegetables were discussed.
```

Configuration:

```text
stable_provider_name_surrogates=True
provider_aliases_by_provider_id={
    "Provider/synthetic-chen": ["Chen"],
    "Provider/synthetic-shore": ["Lena Shore"],
}
provider_name_secret_env_var="PROJECT_PHI_PROVIDER_NAME_SECRET"
```

Expected behavior:

- Provider aliases are not inferred from note text.
- pyDeid-detected spans matching explicit provider aliases use deterministic
  fake provider identities keyed by `provider_id`, secret, and pinned runtime
  environment.
- Supplied provider aliases that pyDeid misses or prunes can still be replaced
  by a bounded exact residual pass.
- Full aliases such as `Lena Shore` can match exactly.
- Single-token aliases such as `Chen` require provider-role context, such as
  `Radiologist Chen`.
- Configured single-token names are not replaced globally in ordinary text, so
  `Green vegetables` remains unchanged unless `Green` appears in provider-role
  context.
- Unknown or unconfigured names remain pyDeid replacements unless the Python
  patient batch API explicitly stabilizes remaining unknown-name spans.

Example output shape:

```text
Radiologist <stable fake provider family name> reviewed mammography.
Copy to <stable fake provider full name> after review.
Green vegetables were discussed.
```

Relevant provider span metadata:

```text
replacement_source="project_stable_provider_name"
project_name_policy="known_provider_alias"
name_role="known_provider_alias"
alias_match_type="full" or "given" or "single_token"
```

If pyDeid prunes a supplied provider alias before ProjectPHI sees it, the
residual span uses:

```text
replacement_source="project_residual_provider_alias"
project_name_policy="residual_explicit_provider_alias"
name_role="known_provider_alias"
alias_match_type="full" or "single_token"
```

## Protected Clinical Term False-Positive Veto

Input:

```text
Current imaging: bilateral mammography with tomosynthesis showed no suspicious mass.
```

Configuration:

```text
include_builtin_protected_clinical_terms=True
```

Expected behavior:

- Protected terms do not detect new PHI.
- If pyDeid emits no PHI span for the clinical phrase, ProjectPHI leaves the
  pyDeid output unchanged.
- If pyDeid emits a span whose whole normalized text exactly matches a
  protected clinical term such as `tomosynthesis`, reconstruction preserves the
  original clinical term instead of pyDeid's replacement.
- For selected risky eponym components, preservation can require exact phrase
  context, for example preserving `Chelsea` only inside `Chelsea Critical Care
  Physical Assessment Tool`.
- No substring, fuzzy, stemming, lemmatization, span expansion, or full-note
  scanning is used.

Observed current output for this example:

```text
Current imaging: bilateral mammography with tomosynthesis showed no suspicious mass.
```

No protected-term span metadata is created when pyDeid emits no span. Relevant
span metadata, if pyDeid does flag a protected term in another note:

```text
action="preserved"
replacement_source="project_protected_clinical_term"
project_protected_term_policy="exact_normalized_span_match"
project_protected_term_rule_id="<configured or built-in rule ID>"
project_protected_term_category="<clinical category>"

or, for context-bound components:

project_protected_term_policy="exact_normalized_component_within_phrase"
project_protected_component="<normalized component>"
project_protected_within_phrase="<normalized approved phrase>"
```

Residual risk remains: a rare person, facility, or organization could share a
protected clinical term. This tradeoff is only for internal training-candidate
generation.

## Title-Context Action-Word Veto

Input:

```text
The Dr. examined the patient. Dr. Solen reviewed mammography.
Dr. Reviewed mammography with tomosynthesis.
Nurse Reviewed wound care. Dr. Examined the patient.
Nurse Taylor reviewed wound care.
```

Expected behavior:

- pyDeid remains the detector and may emit `examined` or `reviewed` as
  title-derived name spans.
- ProjectPHI preserves selected lower-case clinical action words when they
  appear in a narrow `Dr.` title context and are not explicit aliases or pyDeid
  name-list words.
- Capitalized action words are preserved only with specific following clinical
  object context, such as `Dr. Reviewed mammography`.
- Capitalized action words can also be preserved in recognized clinical-role
  contexts, such as `Nurse Reviewed wound care`.
- Generic patient/person context is allowed with the same safety guards, such
  as `Dr. Examined the patient`.
- If pyDeid also emits the adjacent clinical object as a title-derived name
  span, ProjectPHI may preserve that object as part of the same false-positive
  pattern.
- If pyDeid emits a role/title name followed by a lower-case action-word span,
  ProjectPHI may preserve only the action word and still replace the name.
- Incomplete fragments such as `Dr. Examined the` still fall back to pyDeid
  replacement.

Example output shape:

```text
The Dr. examined the patient. Dr. <pyDeid-name-surrogate> reviewed mammography.
Dr. Reviewed mammography with tomosynthesis.
Nurse Reviewed wound care. Dr. Examined the patient.
Nurse <pyDeid-name-surrogate> reviewed wound care.
```

Relevant span metadata:

```text
action="preserved"
replacement_source="project_title_context_action_word_veto"
project_title_context_policy="title_context_action_word_exact_match"
project_title_context_trigger="strict_title_name_heuristic"
project_title_context_word="examined" or "reviewed"

or, for the capitalized clinical-object rule:

project_title_context_policy="title_context_capitalized_action_word_clinical_object_match"
project_title_context_trigger="strict_title_name_heuristic_with_clinical_object"

project_title_context_policy="title_context_capitalized_action_word_generic_patient_object_match"
project_title_context_trigger="strict_title_name_heuristic_with_generic_patient_object"

project_title_context_policy="role_context_capitalized_action_word_clinical_object_match"
project_title_context_trigger="clinical_role_context_with_clinical_object"

project_title_context_policy="role_context_lowercase_action_word_clinical_object_after_name_match"
project_title_context_trigger="adjacent_role_or_title_name_before_action_word"

or, for an adjacent clinical-object span preserved after a title/action word:

project_title_context_policy="title_context_clinical_object_after_action_match"
project_title_context_trigger="strict_title_name_heuristic_after_action_word"
```

## Custom Regex Pass-Through

Input:

```text
Synthetic accession SYN-ACC-1234 was reviewed with stable findings.
```

Configuration:

```python
custom_regexes = {
    "synthetic_accession": {
        "phi_type": "Synthetic Accession",
        "pattern": r"\bSYN-ACC-\d{4}\b",
        "replacement": "<SYNTHETIC_ACCESSION>",
    }
}
```

Expected behavior:

- ProjectPHI validates the config and converts it to a pyDeid custom regex
  object.
- pyDeid performs matching, pruning, and initial replacement.
- ProjectPHI does not scan the note text with the regex as a separate
  detector.
- Raw regex patterns are not copied into span metadata, audit rows, warnings,
  or CLI output.
- The configured `phi_type` is used by pyDeid during replacement. Avoid
  built-in pyDeid type words such as `MRN`, `Name`, `Date`, `Time`, or
  `Hospital` in custom `phi_type` values if you want the configured constant
  `replacement` to appear in the final text.

Example output shape:

```text
Synthetic accession <SYNTHETIC_ACCESSION> was reviewed with stable findings.
```

Relevant span metadata:

```text
custom_regex_rule_id="synthetic_accession"
custom_regex_phi_type="Synthetic Accession"
pydeid_types=["Synthetic Accession", ...]
```

## CSV Row Handling And Audit

Input CSV shape:

```csv
patient_id,encounter_id,note_id,note_text
Patient/synthetic-001,Encounter/synthetic-001,Note/synthetic-001,"Seen on March 14, 2026."
Patient/synthetic-002,Encounter/synthetic-002,Note/synthetic-002,"Patient Zylanda Qorven attended."
```

Configuration:

```text
deidentify_csv(...)
audit_output_file="synthetic_audit.csv"
stable_date_shift=True
stable_patient_name_surrogates=True
patient_aliases_by_patient_id={"Patient/synthetic-002": ["Zylanda Qorven"]}
stable_provider_name_surrogates=True
provider_aliases_by_provider_id={"Provider/synthetic-chen": ["Chen"]}
```

Expected behavior:

- `deidentify_csv(...)` applies `deidentify_note(...)` row by row.
- It does not call pyDeid's CSV workflow.
- Successful output rows preserve input column order and replace only the note
  text column.
- Failed rows are omitted from output, `rows_failed` increments, and warnings
  are sanitized.
- Audit rows are internal artifacts. They include offsets, labels, explicit
  project replacement metadata, explicit pyDeid replacement metadata, pyDeid
  types, and project policy metadata, but omit raw full note text and raw
  detected `span.text`.

Example summary shape:

```python
{
    "rows_read": 2,
    "rows_written": 2,
    "rows_failed": 0,
    "spans_written": 3,
    "warnings": [],
}
```

If a row fails because stable patient-name surrogates are enabled but aliases
are missing, the summary shape is:

```python
{
    "rows_read": 2,
    "rows_written": 1,
    "rows_failed": 1,
    "spans_written": 1,
    "warnings": ["Row failed: row=2, patient_id='...', encounter_id='...', note_id='...', error=ValueError"],
}
```

## CLI Behavior

Command shape:

```bash
project-phi-deid synthetic_input.csv synthetic_output.csv \
  --audit-output-file synthetic_audit.csv \
  --stable-date-shift \
  --date-shift-secret-env-var PROJECT_PHI_DATE_SHIFT_SECRET \
  --no-shift-partial-month-day-dates \
  --stable-patient-name-surrogates \
  --patient-alias-manifest synthetic_aliases.csv \
  --patient-name-secret-env-var PROJECT_PHI_PATIENT_NAME_SECRET \
  --stable-provider-name-surrogates \
  --provider-alias-manifest synthetic_providers.csv \
  --provider-name-secret-env-var PROJECT_PHI_PROVIDER_NAME_SECRET \
  --custom-regex-json synthetic_regexes.json \
  --protected-clinical-terms-csv synthetic_protected_terms.csv
```

Expected behavior:

- The CLI loads config files and calls `deidentify_csv(...)`.
- It accepts secret environment-variable names, not direct secret values.
- It prints summary counts and sanitized warnings only.
- It does not print raw notes, raw aliases, regex patterns, detected PHI,
  secrets, hashes, or HMAC digests.
