# ProjectPHI Behavior

This page documents behavior added by ProjectPHI on top of pyDeid.

## Public Model

ProjectPHI wraps pyDeid output in two dataclasses:

- `PHISpan`: one normalized span with original-note offsets, pyDeid labels/types,
  replacement metadata, provenance, action, and policy metadata.
- `DeidentificationResult`: de-identified text, spans, warnings, and result
  metadata.

`PHISpan.start` and `PHISpan.end` always refer to the original note.

## Span Normalization

`src/project_phi/normalization.py` converts pyDeid surrogate records to
`PHISpan` instances. A surrogate record is one pyDeid-emitted PHI record from
the `surrogates` output. Normalization keeps:

- original span offsets and text in memory;
- pyDeid type labels;
- pyDeid replacement text;
- pyDeid surrogate offsets;
- optional patient/encounter/note IDs in metadata;
- custom regex provenance when a pyDeid type matches configured project custom
  regex metadata.

Persistent audit outputs omit raw detected PHI text by default.

When stable patient-name surrogates are enabled, ProjectPHI may add additional
`PHISpan` records after normalization for supplied patient aliases that pyDeid
did not emit as final spans. These residual spans have original-note offsets,
`source="ProjectPHI.residual_alias"`, and are limited to bounded exact matches
against the explicit alias profile for the current patient.

When stable provider-name surrogates are enabled, ProjectPHI may also add
residual provider-alias spans for supplied provider aliases that pyDeid did not
emit. These spans use `source="ProjectPHI.residual_provider_alias"`. Full
provider aliases can match exactly; single-token provider aliases require local
provider-role context such as `Radiologist Chen` or `Social worker Green`.

## Reconstruction

`src/project_phi/reconstruction.py` rebuilds the final text from original-note
offsets when project policies need to differ from pyDeid's already-replaced
text. Reconstruction is used for:

- stable date shifting;
- stable patient-name surrogates;
- stable provider-name surrogates;
- protected clinical term preservation;
- narrow clinical abbreviation preservation;
- strict obstetric-history shorthand preservation;
- dotted decimal-like contact preservation;
- compact clinical-code and report-fragment preservation;
- ordinary clinical prose and non-geographic vendor/reference preservation;
- ordinary-token false-positive preservation;
- title-token-fragment preservation;
- title-context action-word preservation.

**Default configuration:** stable date shifting, stable patient-name
surrogates, and stable provider-name surrogates are opt-in. Span-local
semantic-preservation vetoes are available by default, so reconstruction may
run even when no stable replacement mode is enabled. Disabling the built-in
protected clinical term list disables only that list; it does not disable other
span-local vetoes.

Reconstruction prunes deterministic pyDeid overlaps, such as nested fragments
or same-source/same-label conflicts where one span is clearly safer to keep.
When overlapping pyDeid contact/OHIP spans cover strongly phone-like text,
ProjectPHI collapses the full run to `<CONTACT>` and audits
`replacement_source="project_contact_overlap_repair"`.
Unresolved mixed overlaps still fail closed with a sanitized error because
silently skipping them could preserve raw text.

Priority order during reconstruction:

1. protected clinical term veto;
2. clinical abbreviation vetoes, such as preserving `PMHx`, standalone
   bounded-token `PMH`/`pmh`, and selected context-bound clinical
   abbreviations such as `SAH`, `MSH`, `WES`, `SAM`, or `AMAN`;
3. strict obstetric-history shorthand vetoes such as `G1P0A0`;
4. stable date shifting, including preservation of score/fraction notation that
   pyDeid emitted as a date-like span;
5. stable patient-name surrogate policy;
6. stable provider-name surrogate policy;
7. dotted decimal-like contact vetoes;
8. compact clinical-code and report-fragment vetoes;
9. ordinary clinical prose and non-geographic vendor/reference vetoes;
10. ordinary-token vetoes for selected pyDeid name false positives;
11. title-token-fragment vetoes for pyDeid-split `Dr.` fragments in strong
   title/name or clinical-role/title/name contexts;
12. title-context action-word veto;
13. pyDeid replacement fallback.

## Stable Date Shifting

When `stable_date_shift=True`, ProjectPHI replaces pyDeid randomized date
replacement with a deterministic per-patient shift:

- `patient_id` is required;
- a secret is required directly or through `date_shift_secret_env_var`;
- the shift offset is deterministic for the same `patient_id` and secret;
- the default range is inclusive `[-45, +45]` days.

The project shifts only pyDeid-detected/pruned date spans it can safely parse.
Current support includes ISO-style full dates, common English month-name full
dates such as `March 14, 2026`, day-month-year forms such as
`8 August 2019`, and month/year spans such as `March 2021`, but only inside
pyDeid-detected date spans. Month/day shifting is available for partial dates
such as `July 15`. Slash date ranges that pyDeid emits as date-range spans are
shifted endpoint-by-endpoint. The project does not scan the full note for
dates.

One narrow exception is compact slash date ranges without spaces around the
hyphen, such as `8/31/18-2/21/2018`. These are shielded before pyDeid to avoid
a pyDeid parser crash, then reconstructed from original offsets as project
date-range spans.

Month/year spans keep month/year granularity. The project uses the same
patient-specific day offset as full dates with an internal day-15 anchor, then
outputs only `Month YYYY`.

Partial month/day spans keep month/day granularity by default. The project uses
an internal leap-year anchor for arithmetic and outputs only `Month Day`.

Times, year-only spans, holidays, and seasons are preserved by default.
Unsupported date-like spans may be replaced with `<DATE>` with sanitized
warnings.

Slash-form score, ratio, staging, node-count, and visual-acuity text can look
like dates to pyDeid, for example `1/50`, `11/50`, `1/61`, or `6/60`. When
pyDeid emits one of these as a date-like span and nearby clinical context
supports a score/fraction reading, ProjectPHI preserves the original text
instead of shifting it to a month/year expression.

## Decimal-Like Contact Vetoes

pyDeid can emit dotted numeric code fragments such as `189.1000043` as
`Telephone/Fax`. ProjectPHI preserves these when the dotted digit grouping is
not phone-like, or when a colon/dotted continuation shows the span is part of a
larger code. Dotted phone numbers such as `416.555.1212` continue to be
replaced.

## Clinical Abbreviation Vetoes

ProjectPHI includes narrow span-local vetoes for observed clinical
abbreviation false positives. pyDeid can emit `PMH` as a `Site Acronym` inside
`PMHx`; ProjectPHI preserves the emitted `PMH` span when the next original
character is `x` or `X`, leaving the clinical abbreviation intact. It also
preserves standalone `PMH`/`pmh` as a bounded token while avoiding matches
inside larger words such as `PMHC` or `pmhClinic`. Selected short
abbreviations such as `NIA`/`AA` in `NIA-AA`, `SAH`, `MSH`, `WES`, `SAM`, or
`AMAN` are preserved only when nearby context supports a specific clinical
meaning.

## Obstetric-History Shorthand

Strict `G/P/A/L/T` obstetric-history shorthand can look identifier-like.
ProjectPHI preserves pyDeid-emitted spans that exactly match conservative
patterns such as `G1P0`, `G1P0A0`, or `G3T1P1A1L2`. This is a span-local veto;
it does not scan the full note for obstetric history and does not preserve
arbitrary alphanumeric study codes.

## Ordinary-Token Vetoes

ProjectPHI includes a narrow span-local veto for selected ordinary tokens that
pyDeid emits as `NAME` spans. The current policy preserves high-confidence
pronoun/article tokens such as `a`, `An`, `He`, and `Her` when local context
does not look like an initial or case label. It also preserves guarded shorthand
or split-token artifacts such as `NH resident` and `at 10 weeks' gestation`.

This is not a general common-word detector. Contexts such as `A. Smith`,
`Dr. A`, `Patient A`, `Subject A`, and `Case A` continue to use pyDeid
replacement behavior.

## Stable Patient-Name Surrogates

When `stable_patient_name_surrogates=True`, ProjectPHI can override pyDeid
name replacements for explicit patient aliases:

- `patient_id` is required;
- a patient-name secret is required directly or through
  `patient_name_secret_env_var`;
- explicit aliases are required;
- pyDeid name detection must be enabled.

The project does not infer aliases from note text. Outside the explicit
patient batch unknown-name mode, unknown name spans keep pyDeid replacement
behavior and can be marked as `unknown_name_pydeid` when reconstruction
metadata is present.

Explicit aliases are first passed to pyDeid through custom patient name-list
hooks where possible. After pyDeid pruning, ProjectPHI also performs a bounded
exact residual pass over only the supplied aliases for that patient. This can
replace aliases such as a full patient name that pyDeid considered ambiguous
and pruned. The residual pass uses word/number boundaries, prefers longer
aliases before shorter components, skips ranges already occupied by pyDeid
spans, and does not search for unknown names.

For matching explicit patient aliases, the fake identity is generated with
deterministic Faker seeded from patient_id and the patient-name secret.
ProjectPHI prefers Faker's Canadian English locale (en_CA) for these stable
patient-name surrogates, falls back to Faker's default locale if that locale is
not available, and uses the tiny in-source name pools only as an emergency
fallback. Callers may provide explicit `feminine`, `masculine`, or `neutral`
fake given-name style metadata. The wrapper does not infer style from the
original alias, note text, diagnosis, or pronouns. Exact fake names may vary if
the runtime Faker version/provider data changes, so deployments that require
byte-for-byte stable surrogates should pin their environment.

Residual alias replacements are audited with
`replacement_source="project_residual_patient_alias"` and
`project_name_policy="residual_explicit_patient_alias"`. pyDeid-detected alias
spans continue to use `replacement_source="project_stable_patient_name"`.

## Stable Provider-Name Surrogates

When `stable_provider_name_surrogates=True`, ProjectPHI can override pyDeid
name replacements for explicit provider aliases:

- provider aliases are required as a mapping from `provider_id` to aliases;
- a provider-name secret is required directly or through
  `provider_name_secret_env_var`;
- pyDeid name detection must be enabled.

Provider aliases are governed runtime configuration, not a provider detector.
ProjectPHI does not infer provider names from note text. Outside the explicit
patient batch unknown-name mode, unknown names keep pyDeid replacement behavior
and can be marked as `unknown_name_pydeid` when reconstruction metadata is
present.

Explicit provider aliases are first passed to pyDeid through custom doctor
name-list hooks where possible. After pyDeid pruning, ProjectPHI performs a
bounded exact residual pass over only configured provider aliases. Full aliases
such as `Lena Shore` can match exactly without role context. Single-token
aliases such as `Chen`, `Green`, or `Cook` require nearby provider-role context
such as `Radiologist Chen`, `Social worker Green`, or a nearby `MD` marker.
This prevents configured common-word-like names from being replaced globally.
Duplicate aliases across provider IDs are allowed. A duplicate alias collapses
to one shared ambiguous-provider surrogate keyed by the alias text and
provider-name secret. This preserves de-identification and text coherence, but
the duplicate alias is not suitable for provider-level identity analysis.

Provider fake identities are deterministic per `provider_id` and provider-name
secret. They use the same Faker-backed generation path as stable patient names,
with the same caveat that exact fake names can vary if the runtime Faker
version/provider data changes.

Provider alias replacements are audited with
`replacement_source="project_stable_provider_name"` for pyDeid-emitted spans or
`replacement_source="project_residual_provider_alias"` for residual spans.
Policy metadata uses `project_name_policy="known_provider_alias"` or
`project_name_policy="residual_explicit_provider_alias"`,
`name_role="known_provider_alias"`, and `alias_match_type` values such as
`full`, `given`, or `single_token`. Duplicate aliases use
`project_name_policy="ambiguous_provider_alias"` and `alias_match_type` values
such as `ambiguous_full` or `ambiguous_single_token`.

## Patient Timeline Unknown-Name Surrogates

`deidentify_patient_notes(...)` can optionally stabilize remaining unknown
pyDeid `NAME` spans within one patient's supplied notes:

- `patient_id` is required;
- an unknown-name secret is required directly or through
  `unknown_name_secret_env_var`;
- single-note, CSV, and CLI defaults remain unchanged unless the mode is
  explicitly enabled.

This mode does not detect new names and does not infer patient/provider roles.
It builds a patient-local registry from pyDeid name spans left after explicit
patient aliases, explicit provider aliases, and semantic-preservation vetoes.
Full names receive one deterministic fake full name. A later standalone given
or family component links back to that full-name surrogate only when the
component is unique in the patient's batch. Ambiguous standalone components
receive their own stable standalone surrogate.

Unknown-name replacements use
`replacement_source="project_stable_unknown_name"`,
`project_name_policy="stable_unknown_name_within_patient"`,
`name_role="unknown_name"`, and `alias_match_type` values such as `full`,
`linked_given`, `linked_family`, or `standalone`.

For CSV/CLI, `stable_unknown_name_surrogates=True` groups rows by
`patient_id_column`, runs the patient batch policy per group, and writes
successful rows back in original input order. Rows without a patient ID fail
through the existing sanitized row-failure path.

## Protected Clinical Terms

Protected clinical terms are a span-local false-positive veto. If pyDeid emits
a span whose whole normalized text exactly matches a protected term,
ProjectPHI preserves the original clinical term instead of using pyDeid's
replacement.

ProjectPHI also supports a narrower phrase-context mode for risky eponym
components. For example, a pyDeid-emitted `Chelsea` span can be preserved when
it sits inside `Chelsea Critical Care Physical Assessment Tool`, but the bare
name-like token `Chelsea` is not globally protected. This avoids converting
clinical tool names into surrogate names while still letting pyDeid replace
person/facility-like uses of the same word.

This is not PHI detection and does not scan the full note. It is a semantic
preservation policy with residual risk: a rare person, facility, or
organization could share a protected term.

## Title-Context Action Words

Title-context action words are another span-local false-positive veto. If
pyDeid emits a clinical action word as a title-derived `NAME` span, ProjectPHI
can preserve the original word when the context is a narrow `Dr.` title pattern
or recognized clinical-role context.

This is intended for cases such as `The Dr. examined the patient` or
`Dr. Solen reviewed mammography`, where pyDeid may treat `examined` or
`reviewed` as a name. Lower-case action words use the base rule. Capitalized
action words, such as `Dr. Reviewed mammography`, require additional following
clinical-object context because capitalized tokens after `Dr.` are more likely
to be real names. Generic patient/person context, such as
`Dr. Examined the patient`, is allowed only after the action-word and pyDeid
name-list guards pass. Role contexts such as `Nurse Reviewed wound care` or
`Radiologist Reviewed mammography` use the same guards. If pyDeid also emits
the following clinical object as a title-derived name span, ProjectPHI can
preserve that adjacent object as part of the same false-positive title/action
pattern. If pyDeid emits a real/plausible name after a role and then emits an
adjacent lower-case action word as another name span, ProjectPHI can preserve
only the action word while leaving the name replacement intact, for example
`Nurse Taylor reviewed wound care` -> `Nurse <name> reviewed wound care`.

ProjectPHI also has a narrower title-token-fragment veto for cases where pyDeid
splits a non-identifying `Dr.` token itself into name spans, such as `D` and
`r.` after `family physician`. The veto preserves only fragments inside the
exact title token and only when a strong clinical-role/title/name or
title/name context is present. The actual clinician name spans still use
pyDeid replacement unless another explicit project policy, such as stable
provider-name surrogates, applies.

## CSV Adapter

`deidentify_csv(...)` applies `deidentify_note(...)` row by row. It preserves
all input columns for successful rows and replaces only the configured note text
column. Failed rows are omitted, counted, and represented by sanitized warnings.

## Audit Output

Audit CSVs are project-specific internal artifacts. They include offsets,
explicit project and pyDeid replacement metadata, pyDeid types, project policy
metadata, and sanitized row warnings. They omit raw note text and raw detected
PHI text by default. 

## CLI And Config Loaders

The CLI (`python -m project_phi.cli` or `project-phi-deid`) wraps
`deidentify_csv(...)`.

Config loaders parse:

- patient alias manifest CSV;
- provider alias manifest CSV;
- custom regex JSON;
- protected clinical terms CSV.

They do not run detection, infer aliases, or print sensitive config values.
