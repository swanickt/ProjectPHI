# Privacy And Audit Notes

## Output CSV vs Audit CSV

The de-identified output CSV is the pipeline output intended for downstream review and possible training preparation.

The audit CSV is different. It is an internal audit artifact for debugging, governance review, and error analysis. It should not be treated as training data.

## Why Audit CSVs Should Stay Internal

Audit rows may include:

- fake replacement text;
- shifted project date replacements;
- exact project replacement offsets;
- exact pyDeid surrogate offsets;
- date-shift offset metadata;
- span labels and pyDeid type metadata;
- preserved protected clinical term replacement text and policy metadata;
- preserved title-context action words and policy metadata;
- preserved title-token fragments such as `Dr.` pieces and policy metadata;
- preserved ordinary-token or clinical-abbreviation text and policy metadata;
- preserved obstetric-history shorthand text and policy metadata;
- stable residual explicit patient-alias replacement metadata;
- stable explicit provider-alias replacement metadata;
- patient, encounter, or note identifiers if configured in input columns.

This information is useful for review, but it is more detailed than ordinary training output should need.

## What Should Not Appear In Audit Or Warnings

Audit output and warning text should not include:

- raw note text;
- raw detected PHI text;
- `span.text`;
- raw regex patterns;
- secrets;
- HMAC digests;
- raw hashes;
- raw alias lists.

The current audit writer includes explicit project replacement metadata
(`project_replacement`, `project_replacement_start`, `project_replacement_end`)
and explicit pyDeid replacement metadata (`pydeid_replacement`,
`pydeid_surrogate_start`, `pydeid_surrogate_end`), but omits raw detected text.
Warning rows are sanitized and use row number,
configured IDs, warning index/type, and exception class rather than arbitrary
exception text.

## Warning And Error Sanitization

CSV row failures are handled through the row-failure path:

- the failed row is omitted from output;
- `rows_failed` is incremented;
- a sanitized warning is added to the returned summary;
- a warning-only audit row is written when audit output is enabled.

The warning formatter intentionally avoids copying arbitrary exception messages because those messages could contain raw note text or detected PHI.

## Patient Alias Manifests

Stable patient-name surrogates require explicit aliases. The pipeline does not
infer aliases from note text because notes may include patient names, clinician
names, family names, copied-correspondence names, facilities, and organizations.
Guessing could incorrectly assign a non-patient name to the patient identity and
over-replace clinically useful role information.

If CSV stable patient-name surrogates are enabled and a row has no aliases, the
row uses the same sanitized row-failure path: it is omitted from output,
`rows_failed` increments, and summary/audit warnings do not include raw note
text, raw aliases, or detected PHI. If stable patient-name surrogates are
disabled, pyDeid still replaces names normally, but its generated replacements
may differ across notes for the same patient.

When aliases are supplied, ProjectPHI can exact-match only those aliases after
pyDeid to catch values pyDeid pruned. Residual alias audit rows record policy
metadata such as `replacement_source="project_residual_patient_alias"` and
`project_name_policy="residual_explicit_patient_alias"`, but the audit writer
still omits raw alias text and raw detected PHI text.

Stable date shifting is separate from alias handling. It can be stable across
notes using `patient_id` and a date-shift secret, without a patient alias
manifest.

## Provider Alias Manifests

Stable provider-name surrogates require explicit provider aliases keyed by
provider ID. Provider aliases are governed runtime configuration, not a public
provider list and not a provider detector. The pipeline does not infer provider
names from note text.

When provider aliases are supplied, ProjectPHI can exact-match only those
aliases after pyDeid to catch values pyDeid missed or pruned. Full aliases can
match exactly. Single-token aliases require local provider-role context, which
reduces the risk of replacing common words globally.

Provider alias audit rows record policy metadata such as
`replacement_source="project_stable_provider_name"` or
`replacement_source="project_residual_provider_alias"`, plus
`project_name_policy` and `name_role="known_provider_alias"`. The audit writer
still omits raw alias text and raw detected PHI text.

## Protected Clinical Terms

Protected clinical terms are internal semantic-preservation false-positive
vetoes. They only apply to pyDeid-detected/pruned spans and do not scan the
full note or detect PHI. When a pyDeid span exactly matches a protected
clinical term, output and audit replacement fields may contain that clinical
term because it is intentionally preserved.
For selected risky eponym components, protected-term policy may also record the
approved phrase context that allowed preservation. Those fields are still
internal audit metadata, not training output.

The built-in protected term set is manually curated, general, and
non-site-specific. It is a targeted breast/oncology/radiology and selected
clinical tool/scale/criteria semantic-preservation set, not a bulk terminology
export. ProjectPHI relies on pyDeid's internal medical/common-word resources
only through pyDeid's normal runtime behavior.

Larger terminology-derived protected-term lists should be governed runtime
artifacts passed with `--protected-clinical-terms-csv`, not committed to the
public repository. 

This accepts residual risk for internal training candidate generation: a rare
person, facility, or organization name could match a protected clinical term.
Protected-term preservation is not a legal/compliance guarantee and does not
make output safe for external release. Real governed use requires
institutional, legal, and governance review.


## Title-Context Action Words

Title-context action-word vetoes preserve selected clinical verbs that pyDeid
emitted as title-derived name spans in narrow `Dr.` or clinical-role contexts.
Lower-case verbs use the base `Dr.` rule; capitalized verbs require specific
following clinical-object context or generic patient/person context, and
adjacent clinical-object spans may be preserved as part of the same bounded
pattern. Lower-case action words immediately after a replaced role/title name
span may also be preserved. Title-token-fragment vetoes separately preserve
non-identifying `Dr.` fragments when pyDeid split the title token itself in a
strong title/name or clinical-role/title/name context. Audit rows may include
the preserved action word, preserved title fragment, or
clinical object as `project_replacement` plus policy metadata such as
`project_title_context_policy` or `project_title_token_policy`. This is an
internal semantic-preservation
artifact, not evidence that the output is safe for external release.

## Custom Regex Privacy

Custom regex patterns may reveal local identifier conventions. The project validates patterns but does not echo raw patterns in validation errors, span metadata, audit output, or warnings.

pyDeid performs the actual custom regex matching. The project wrapper suppresses local pyDeid stdout for custom regex calls because this local pyDeid version prints supplied custom regex objects.

## Secret Handling

Date shifting, patient-name surrogate generation, and provider-name surrogate
generation use runtime secrets. Secrets can be supplied directly or by
environment variable. Recommended environment variables:

- `PROJECT_PHI_DATE_SHIFT_SECRET`
- `PROJECT_PHI_PATIENT_NAME_SECRET`
- `PROJECT_PHI_PROVIDER_NAME_SECRET`

Do not commit secrets. Do not write secrets, HMAC digests, or raw hashes into output or audit files.

## Limitations

This pipeline is a pyDeid-based internal risk-reduction tool. Regex/list-based de-identification can miss identifiers and can sometimes replace clinically meaningful text. Stable replacement improves longitudinal consistency for selected PHI classes, but it does not prove that text is anonymous or legally de-identified.

The pipeline requires empirical validation and governance review for any governed dataset or downstream use.
