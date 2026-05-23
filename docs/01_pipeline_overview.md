# Pipeline Overview

This page is a compact overview. For more details, see:

- [Architecture](02_architecture.md)
- [pyDeid Behavior](03_pydeid_behaviour.md)
- [ProjectPHI Behavior](04_ProjectPHI_behaviour.md)
- [Semantic Preservation](07_semantic_preservation.md)
- [Privacy And Audit Notes](06_privacy_and_audit_notes.md)
- [Examples](08_examples.md)

## High-Level Flow

```text
note text
  -> pyDeid deid_string(...)
       - detection
       - pruning/overlap handling
       - initial surrogate generation
  -> normalize pyDeid surrogate records into PHISpan
  -> optional residual explicit patient/provider alias span creation
  -> optional project reconstruction from original-note offsets
       - protected clinical term veto
       - clinical abbreviation veto
       - obstetric-history shorthand veto
       - stable date shifting
       - stable patient-name aliases
       - stable provider-name aliases
       - dotted decimal-like contact veto
       - ordinary-token veto
       - title-token-fragment veto
       - title-context action-word veto
       - pyDeid replacement fallback
  -> DeidentificationResult
```

**ProjectPHI** is pyDeid-first. It does not add NER, an LLM verification step,
or an external API call. pyDeid remains the source of general PHI detection,
pruning, built-in regex/list behavior, custom regex matching, custom name-list
handling, and base surrogate generation. The narrow exceptions are stable
patient-name and stable provider-name modes: when explicit aliases are supplied,
ProjectPHI can create residual spans for exact alias matches that pyDeid pruned
before final output. Provider single-token residual aliases require local
provider-role context. These passes check only caller-supplied aliases and do
not infer arbitrary names.

## What pyDeid Provides

The wrapper calls pyDeid `deid_string(...)` through
`src/project_phi/pydeid_client.py`. pyDeid returns surrogate records and
pyDeid's own de-identified text. **ProjectPHI** preserves pyDeid behavior unless
a documented project policy needs a stable replacement or semantic-preservation
veto.

In these docs, a pyDeid "surrogate record" means one table-like record from
pyDeid's `surrogates` output for a detected PHI span. `src/project_phi/normalization.py` converts each pyDeid surrogate
record into one `PHISpan` object.

pyDeid internal wordlists and gazetteers are used only through normal pyDeid
runtime behavior.

## What ProjectPHI Adds

**ProjectPHI** adds:

- `PHISpan` and `DeidentificationResult` dataclasses;
- explicit metadata separation for original offsets, pyDeid surrogate offsets,
  and project-final replacement offsets;
- a single-note wrapper, CSV adapter, config loaders, and CLI;
- internal audit CSV output;
- stable per-patient date shifting for supported pyDeid-detected full dates,
  month/year spans, and month/day spans;
- stable patient-name surrogates for explicit aliases only, including bounded
  exact residual matching for supplied aliases missed or pruned by pyDeid;
- stable provider-name surrogates for explicit governed aliases only,
  including role-guarded residual matching for single-token provider aliases;
- protected clinical term false-positive vetoes;
- dotted decimal-like contact false-positive vetoes;
- narrow clinical abbreviation and ordinary-token false-positive vetoes;
- title-context action-word false-positive vetoes;
- custom regex configuration that is passed through to pyDeid.

## Reconstruction

When stable dates, stable patient-name surrogates, stable provider-name
surrogates, protected clinical terms, title-token fragments, or title-context
action words are active,
**ProjectPHI** reconstructs final text from original-note offsets. This avoids
editing pyDeid's already-replaced text, where project replacements may have
different lengths and offset systems would become ambiguous.

By default, stable dates, stable patient-name surrogates, and stable
provider-name surrogates are off. The small built-in protected clinical term
set is on, so reconstruction can still run by default when pyDeid emits a span
that a project semantic-preservation rule may preserve. See
[Configuration](05_configuration.md#default-project-policy).


Reconstruction priority:

1. protected clinical term veto;
2. narrow clinical abbreviation vetoes, such as `PMHx`, standalone `PMH` in
   past-medical-history context, and selected context-bound clinical
   abbreviations;
3. strict obstetric-history shorthand vetoes such as `G1P0A0`;
4. stable date shifting, including preservation of score/fraction notation that
   pyDeid emitted as a date-like span;
5. stable patient-name surrogate policy;
6. stable provider-name surrogate policy;
7. dotted decimal-like contact false-positive vetoes;
8. compact clinical-code and duration-phrase vetoes, such as GCS components,
   TNM staging, and strongly contextual biomedical abbreviations;
9. ordinary-token vetoes for selected pyDeid name false positives, such as
   articles/pronouns and guarded `NH` nursing-home shorthand;
10. title-token-fragment vetoes for cases where pyDeid splits a
   non-identifying `Dr.` token into name spans;
11. title-context action-word veto;
12. pyDeid replacement fallback.

Reconstruction fails closed on unexpected overlapping spans rather than
silently preserving raw text.

## CSV, CLI, And Audit

`deidentify_csv(...)` applies `deidentify_note(...)` row by row. It does not use
pyDeid's CSV workflow because the project needs consistent metadata, stable
replacement policies, sanitized row failures, and audit output.

The CLI wraps `deidentify_csv(...)` and prints only summary counts plus
sanitized warnings. Audit CSVs are internal review artifacts, not training
outputs.
