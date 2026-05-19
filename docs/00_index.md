# Documentation Index

**ProjectPHI** is a [pyDeid](https://github.com/GEMINI-Medicine/pyDeid)-based clinical free-text de-identification
wrapper. It is intended to reduce identifier
risk while preserving clinically useful text for downstream review and possible use in machine-learning training.

It is not a legal certification tool. It does not guarantee full text de-identification,
anonymization, PHIPA compliance, HIPAA compliance, or external-release safety.
The current pipeline uses pyDeid as its core PHI detection and replacement engine. **ProjectPHI** wraps this engine with a small set of project-specific controls for consistency, reviewability, and clinical text preservation.

As of now, the project does **not** use named-entity recognition (NER), LLMs, external API calls, a separate PHI detector, its own broad gazetteers, or Sunnybrook/Ontario-specific identifier rules.

The built-in semantic-preservation rules should be treated as the current
stable baseline. Further terminology expansion should come from governed local
evaluation or runtime protected-term CSV artifacts, not broad public built-in
growth.

## Doc Map

- [Pipeline Overview](01_pipeline_overview.md): Single-page, compact, cross-reference overview.
- [Architecture](02_architecture.md): module layout, data flow, pyDeid boundary,
  CSV/CLI/config layers.
- [pyDeid Behavior](03_pydeid_behavior.md): behavior inherited from pyDeid and
  what the wrapper deliberately leaves to pyDeid.
- [ProjectPHI Behavior](04_ProjectPHI_behavior.md): normalized span model,
  reconstruction, stable date/name replacement, protected terms, CSV, CLI.
- [Configuration](05_configuration.md): Python APIs, CLI flags, config file shapes, and
  secrets.
- [Privacy And Audit Notes](06_privacy_and_audit_notes.md): audit CSV boundaries,
  sanitization policy, secret handling, residual risks.
- [Semantic Preservation](07_semantic_preservation.md): date intervals, aliases,
  protected clinical terms, false-positive tradeoffs, external terminology
  source policy.
- [Developer Notes](08_developer_notes.md): testing strategy, safe future changes,
  release/checkpoint checklist.
- [Examples](09_examples.md): synthetic input/output/behavior examples for the
  note, CSV, stable replacement, custom regex, and protected-term workflows.
- [Current Limitations](10_current_limitations.md): known behavior gaps,
  reasons, and possible future mitigations.
