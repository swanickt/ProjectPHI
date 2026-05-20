# Current Limitations

This page tracks known ProjectPHI limitations that are important for evaluation
and future planning. Each item describes the observed problem, the likely
reason, and a potential solution.

ProjectPHI remains pyDeid-first. A limitation listed here is not necessarily a
bug in pyDeid or ProjectPHI; it is a behavior that matters for this project’s
clinical semantic-preservation and risk-reduction goals.

## 1. Explicit Patient Aliases Can Be Pruned Before ProjectPHI Sees Them

### Problem

An explicit patient alias supplied through the alias manifest can remain in the
final output if pyDeid does not emit a final, pruned name span for that alias.

Observed synthetic example:

```text
Input:
Patient Amelia Rowan was seen by Dr. Lena Shore.

Alias manifest:
SYN-P001,Amelia Rowan
SYN-P001,Amelia
SYN-P001,Rowan

Output observed in local smoke testing:
Patient Amelia Rowan was seen by Dr. Richard Gonzalez.
```

The clinician name was replaced, but `Amelia Rowan` remained.

### Reason

ProjectPHI’s stable patient-name surrogate layer only replaces pyDeid-emitted,
pyDeid-pruned name spans that match explicit patient aliases. It does not scan
the whole note for aliases independently.

In the observed case, pyDeid initially identified ambiguous name candidates:

```text
Patient -> Last Name (ambig)
Amelia  -> Female First Name (ambig)
Rowan   -> Last Name (ambig)
seen    -> Last Name (ambig)
Lena    -> stronger title-context name evidence
Shore   -> stronger title-context name evidence
```

After pyDeid pruning, only `Lena` and `Shore` survived as final name spans.
`Amelia` and `Rowan` were ambiguous/common-word-like candidates and were pruned.
Because ProjectPHI receives only the final pyDeid spans, the stable alias layer
had no patient-name span to replace.

This is consistent with the pyDeid-first design, but it is a practical recall
gap for explicit patient aliases.

### Potential Solution

Add an opt-in explicit-alias residual policy after pyDeid processing. Possible
modes:

- `warn`: scan only the provided explicit aliases in final output and emit a
  sanitized warning if any remain.
- `fail_row`: for CSV processing, omit rows where explicit aliases remain after
  de-identification.
- `replace_explicit_aliases`: replace exact matches from the provided alias
  manifest after pyDeid, without detecting arbitrary names.

Important constraints for any future solution:

- do not infer aliases from note text;
- do not scan for arbitrary names;
- do not treat unknown clinician/family/copied-correspondence names as patient
  aliases;
- do not log raw aliases in warnings or audit rows;
- keep behavior configurable because it intentionally goes beyond pyDeid’s
  final pruned span output.

## 2. Reserved-Domain Synthetic Emails May Not Reflect Real Email Behavior

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

## 3. Gender-Neutral Stable Names Can Conflict With Pronouns

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

## 4. Role-Associated Provider Names May Remain If pyDeid Emits No Span

### Problem

Provider or staff names can remain in output when they appear after a clinical
role word that pyDeid does not treat as a strong title/name cue.

Observed synthetic patterns worth tracking:

```text
Radiologist Chen reviewed mammography.
Social worker Green discussed transportation barriers.
Breast surgeon Cook examined the incision.
Surgeon Cook discussed pathology with the patient.
```

### Reason

ProjectPHI remains pyDeid-first. It only replaces or preserves spans that
pyDeid emits after its own detection and pruning. It does not scan the full
note for arbitrary role-name patterns.

pyDeid has finite title/name-context handling. Some role words, such as `Dr.`
or `Nurse`, can help pyDeid identify nearby names. Other role phrases, such as
`radiologist`, `social worker`, `breast surgeon`, `pathologist`, or
`pharmacist`, may not be enough by themselves. Names that are also ordinary
English words, such as `Cook` or `Green`, can be especially easy to miss or
prune because pyDeid intentionally protects common words to preserve semantics.

### Potential Solution

Defer implementation until local evaluation shows this pattern is common
enough to justify a project rule. A future fix should be narrow and opt-in,
for example:

- a governed role/context list for provider-like phrases;
- exact role-context matching only, not broad name scanning;
- one- or two-token capitalized provider candidates after approved role
  phrases;
- safeguards for common clinical action words and protected clinical terms;
- audit metadata showing that a project role-context policy triggered;
- synthetic positive and negative tests.

Provider name resources, if used, should be governed runtime artifacts rather
than public committed provider lists. This should not become a general NER
system or a broad free-text person detector.
