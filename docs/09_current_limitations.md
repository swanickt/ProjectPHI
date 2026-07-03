# Current Limitations

This page tracks known ProjectPHI limitations that are important for evaluation
and future planning. 

ProjectPHI remains pyDeid-first. A limitation listed here is not necessarily a
bug in pyDeid or ProjectPHI; it is a behavior that matters for this project’s
clinical semantic-preservation and risk-reduction goals.

## 1. Gender-Neutral Stable Names Can Conflict With Pronouns

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

