# Longitudinal Timeline De-Identification Plan

## Purpose

This plan covers the two ProjectPHI additions needed for downstream
per-patient timeline construction:

1. expose the patient-specific date-shift offset for tabular OMOP date shifts;
2. optionally make pyDeid-detected unknown names coherent within a patient
   timeline.

ProjectPHI should remain the de-identification component. It should not build
episode tables, evidence registries, or OMOP exports.

## Current State

ProjectPHI already computes one deterministic date offset from `patient_id`,
date-shift secret, and `date_shift_days`. That offset is applied to supported
pyDeid-detected note dates and recorded on shifted date spans.

ProjectPHI already supports stable patient and provider names when explicit
alias manifests are supplied. Unknown name spans still use pyDeid replacement
fallback, so the same unknown string, or a full name and later component of
that name, may receive unrelated replacements across notes.

pyDeid remains the detector, pruner, base replacement engine, custom regex
runner, and custom name-list consumer. ProjectPHI should keep the new behavior
in the wrapper/reconstruction layer.

## 1. Public Patient Date-Shift Offset

### Goal

Expose the same patient-specific integer offset used for note text so a
downstream timeline builder can shift structured OMOP dates consistently.

### Proposed API

Add a public helper, for example:

```python
from project_phi import get_patient_date_shift

offset = get_patient_date_shift(
    patient_id="123",
    date_shift_secret_env_var="PROJECT_PHI_DATE_SHIFT_SECRET",
    date_shift_days=45,
)
```

The helper should return only the bounded integer day offset. It must not return
or expose secrets, HMAC digests, hashes, or intermediate key material.

### Scope

The helper should:

- reuse the existing secret resolution and HMAC offset logic;
- validate `patient_id`, secret, and `date_shift_days` exactly as note shifting
  does;
- be exported from `project_phi.__init__`;
- be documented as the supported API for OMOP/tabular date shifting.

It should not:

- shift OMOP tables directly;
- inspect note text;
- infer patient IDs;
- persist shift manifests by default.

### Tests

Add tests that confirm:

- the helper matches the offset used by `deidentify_note(... stable_date_shift=True)`;
- the same patient and secret produce the same offset across calls;
- different patients or secrets can produce different offsets;
- `date_shift_days=0` returns `0`;
- missing patient ID, missing secret, and invalid range fail cleanly;
- no secret/digest appears in returned values or metadata.

## 2. Per-Patient Timeline Unknown-Name Replacement

### Goal

Optionally make pyDeid-detected unknown names coherent within a patient
timeline, even when they are not explicit patient or provider aliases.

### Proposed API

Prefer a patient-batch API over a single-note flag, for example:

```python
result = deidentify_patient_notes(
    patient_id="123",
    notes=[
        {"note_id": "n1", "note_text": "Maria Lopez called."},
        {"note_id": "n2", "note_text": "Maria called again."},
    ],
    stable_unknown_name_surrogates=True,
    unknown_name_secret_env_var="PROJECT_PHI_UNKNOWN_NAME_SECRET",
)
```

The batch API should run pyDeid over all notes for one patient, build a
patient-local unknown-name registry, then reconstruct each note. CSV support can
be added later by grouping rows by `patient_id`.

The mode should require `patient_id`, a secret, and pyDeid name detection.

### Replacement Policy

Only pyDeid-emitted `NAME` spans should be eligible. The policy should not
detect additional names or add residual unknown-name spans.

Replacement should be deterministic from:

```text
patient_id + normalized unknown-name entity key + unknown-name secret
```

This makes unknown-name replacements stable within the patient while avoiding
cross-patient linkage. Two patients with the same original name should not
receive the same unknown-name surrogate unless explicitly configured otherwise.

Explicit patient aliases and explicit provider aliases must keep priority over
unknown-name replacement. Semantic-preservation vetoes should also keep their
current priority.

### Registry Logic

The batch should first collect pyDeid `NAME` spans across all notes for the
patient, then build a registry:

- full names receive one deterministic fake full identity;
- standalone components link to a full name only when they map uniquely within
  the patient's full batch;
- ambiguous components receive their own deterministic standalone replacement.

Example:

```text
Maria Lopez -> Olivia Chen
Maria       -> Olivia
Lopez       -> Chen
```

Ambiguous example:

```text
Maria Lopez  -> Olivia Chen
Maria Santos -> Rachel Patel
Maria        -> standalone fake given token
```

This preserves the original note's ambiguity without creating extra
inconsistency. The result must be independent of note order.

### Replacement Shape

Use deterministic Faker-backed names, similar to current stable patient/provider
identity generation, but keyed by the per-patient unknown-name registry key.
Preserve the detected span granularity:

- full-name span -> fake full name;
- uniquely linked given component -> linked fake given name;
- uniquely linked family component -> linked fake family name;
- ambiguous or standalone token -> stable standalone fake token.

Avoid storing raw source text, hashes, or HMAC digests in audit output. Audit
metadata can record policy labels such as
`project_name_policy="stable_unknown_name_within_patient"`.

### Risks

This mode can make copied family, provider, outside-clinician, or organization
names more readable and consistent. That helps timeline review, but it may also
make non-patient entities look more coherent across a patient timeline.

For that reason, this should be opt-in and documented as an internal-use
readability/consistency policy, not a PHI detector and not external-release
certification.

### Tests

Add tests that confirm:

- the same unknown full name in two notes for one patient receives the same
  surrogate;
- unique given/family components link back to the fake full-name components;
- ambiguous standalone components do not link to one full name arbitrarily;
- output is independent of note order;
- the same source name for different patients receives different surrogates;
- explicit patient aliases still use stable patient-name policy;
- explicit provider aliases still use stable provider-name policy;
- title-context, ordinary-token, protected-term, and clinical-code vetoes still
  win before unknown-name replacement;
- single-note and CSV row-by-row behavior remains unchanged unless the new
  batch/timeline mode is used;
- audit rows omit raw names, secrets, hashes, and HMAC digests.

## Implementation Order

1. Add and test `get_patient_date_shift`.
2. Add the unknown-name secret resolver and deterministic registry helpers.
3. Add `deidentify_patient_notes(...)` for one-patient batch de-identification.
4. Thread the patient-local registry into reconstruction and audit metadata.
5. Add CSV/CLI grouping support only after the Python batch API is stable.
6. Update relevant docs: README, pipeline overview, ProjectPHI behavior,
   configuration, semantic preservation, privacy/audit notes, examples, and
   current limitations if needed.
7. Run focused tests, then the full suite.
