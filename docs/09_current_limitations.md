# Current Limitations

This page tracks known ProjectPHI limitations that are important for evaluation
and future planning. Each item describes the observed problem, the likely
reason, and a potential solution.

ProjectPHI remains pyDeid-first. A limitation listed here is not necessarily a
bug in pyDeid or ProjectPHI; it is a behavior that matters for this project’s
clinical semantic-preservation and risk-reduction goals.

## 1. Reserved-Domain Synthetic Emails May Not Reflect Real Email Behavior

### Problem

Local smoke testing showed that some intentionally artificial email addresses
using reserved-looking domains remained in output.

Observed synthetic examples:

```text
amelia.rowan@example.invalid
kira.meadow@example.invalid
```

This is worth noting, but it is not currently treated as a major pipeline issue
by itself.

### Reason

ProjectPHI delegates email/contact detection to pyDeid unless a custom regex is
explicitly supplied. The missed examples used synthetic domains intended for
safe documentation/testing, not necessarily the same shapes found in real
clinical notes.

Optimizing the pipeline around unusual synthetic email domains could create
work that does not improve real-world behavior.

### Potential Solution

Prefer realistic-but-synthetic email shapes in future local tests, then check
whether pyDeid detects them:

```text
synthetic.patient@example.com
synthetic.patient@testclinic.ca
synthetic.patient@samplehospital.ca
```

If governed/local evaluation shows realistic email styles are missed, add a
targeted custom regex configuration.

## 2. Gender-Neutral Stable Names Can Conflict With Pronouns

### Problem

Stable patient-name surrogates currently use deterministic fake-name pools that
do not preserve gender presentation. This can make breast oncology notes read
awkwardly when pronouns remain unchanged.

Observed synthetic example:

```text
Input:
Jana Rivers returns after chest wall radiotherapy. She denies dyspnea.

Output:
Robert Stewart returns after chest wall radiotherapy. She denies dyspnea.
```

This is not primarily a privacy failure, but it can reduce readability and
training-data realism.

The notes may still contain `she` or other gendered pronouns. The fake names
are stable and deterministic, but not gender-concordant.

### Reason

ProjectPHI does not infer sex or gender from note text, diagnosis, specialty,
or pronouns. The current stable patient-name identity generation is keyed by
patient ID and secret, and chooses from general fake-name pools.

That conservative design avoids brittle or inappropriate inference. It also
means names and pronouns may not align.

### Potential Solution

Keep the default gender-neutral behavior. If realistic name/pronoun alignment
becomes important, add an optional structured metadata input from a governed
source, for example:

```csv
patient_id,name_style
SYN-P001,feminine
SYN-P002,masculine
SYN-P003,neutral
```

Future constraints:

- do not infer gender from breast cancer, pronouns, or note text;
- do not require this metadata for baseline use;
- treat name style as a formatting control, not as clinical truth;
- keep deterministic selection keyed by patient ID and secret;
- document residual readability and bias tradeoffs.

## 3. Unconfigured Provider Names May Remain If pyDeid Emits No Span

### Problem

Provider or staff names can remain in output when they appear after a clinical
role word that pyDeid does not treat as a strong title/name cue and no governed
provider alias manifest is supplied for those names.

Observed synthetic patterns worth tracking:

```text
Radiologist Chen reviewed mammography.
Social worker Green discussed transportation barriers.
Breast surgeon Cook examined the incision.
Surgeon Cook discussed pathology with the patient.
```

### Reason

ProjectPHI remains pyDeid-first for arbitrary names. It does not scan the full
note for arbitrary role-name patterns or infer provider identities from role
words.

The stable provider-name surrogate mode can address this class only for
explicitly configured provider aliases. In that mode, ProjectPHI can exact-match
supplied full provider aliases and can match supplied single-token provider
aliases only in local provider-role context. Unknown or unconfigured provider
names remain pyDeid behavior.

pyDeid has finite title/name-context handling. Some role words, such as `Dr.`
or `Nurse`, can help pyDeid identify nearby names. Other role phrases, such as
`radiologist`, `social worker`, `breast surgeon`, `pathologist`, or
`pharmacist`, may not be enough by themselves. Names that are also ordinary
English words, such as `Cook` or `Green`, can be especially easy to miss or
prune because pyDeid intentionally protects common words to preserve semantics.

### Potential Mitigation

Use stable provider-name surrogates when governed provider aliases are
available:

- supply a runtime `provider_id,alias` manifest;
- enable `stable_provider_name_surrogates`;
- provide a provider-name secret directly or through an environment variable;
- review audit metadata such as `project_stable_provider_name` and
  `project_residual_provider_alias`.

Provider name resources should remain governed runtime artifacts rather than
public committed provider lists. This mode should not become a general NER
system or a broad free-text person detector.

 ## 4. Date-Shift Audit Metadata Can Appear On Non-Date Spans

  ### Problem

  When stable date shifting is enabled, some audit rows for non-date spans can
  show values in date-specific metadata columns such as
  `project_date_shift_range_days` and `project_date_shift_policy`.

  Example audit rows may show non-date policies in a date-specific column:

  ```text
  NAME    project_date_shift_policy=full
  NAME    project_date_shift_policy=given
  CONTACT project_date_shift_policy=pydeid_replacement
  ```

  The de-identified note text is not affected, and project_date_shift_days is
  only populated for actual shifted date spans. However, the audit CSV can be
  misleading for date-policy review because the date-specific policy column does
  not always describe a date-shift policy.

  ### Reason

  The reconstruction path currently records project_date_shift_range_days and
  project_date_shift_policy whenever date shifting is enabled for the note,
  rather than only when the current span is a date/time/date-like span handled by
  the date policy. For non-date spans, the generic replacement policy value can
  therefore be copied into a date-specific audit column.

  ### Potential Solution

  Restrict date-shift audit metadata to spans actually handled by date policy,
  such as:

  - replacement_source="project_stable_date_shift";
  - preserved_time;
  - preserved_year_only;
  - preserved_holiday_or_season;
  - preserved_score_or_fraction;
  - unparseable_date_placeholder;
  - other explicitly date-like policies.

  Leave date-specific audit columns blank for patient names, provider names,
  contacts, custom regex identifiers, protected clinical terms, ordinary-token
  vetoes, and pyDeid fallback spans.

  This is an audit-cleanliness fix, not a de-identified text correctness fix.