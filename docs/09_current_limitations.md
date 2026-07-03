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

## 4. External 1000-Note Eval Still Has Medium-Priority Precision Candidates

### Problem

The June 8, 2026 rerun of the local 1000-note Open-Patients smoke evaluation,
after the internal semantic-preservation expansion, had no high-priority
semantic, formatting, or obvious residual contact-pattern issues, but it still
produced medium-priority precision candidates where pyDeid replacement may
remove useful source meaning.

Current groups include:

- geography, institution, and care-site metadata intentionally left to pyDeid;
- a few short-fragment cases, such as `de` and person-like `XY`, that are not
  safe to preserve broadly.

### Reason

Many of these strings overlap with person names, institutions, care sites,
vendors, or places. Preserving them globally would increase identifier risk.
The current policy therefore keeps pyDeid fallback unless a rule can be bounded
to a low-risk clinical phrase or governed local policy.

### Potential Solution

Continue adding exact, phrase-bound, or context-bound semantic-preservation
rules for low-risk clinical variants, especially those likely to occur in
breast oncology notes. Keep geography, institutions, care sites, and local
site metadata governed outside the public built-in list.
