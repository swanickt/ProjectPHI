# Architecture

## Data Flow

The core workflow is pyDeid-first:

```text
note text
  -> pyDeid detection, pruning, and initial surrogate replacement
  -> project PHISpan normalization
  -> optional exact residual spans for supplied patient/provider aliases
  -> optional project reconstruction from original-note offsets
  -> de-identified text candidate + structured span metadata
```

ProjectPHI does not run a parallel detector for arbitrary PHI. pyDeid remains
responsible for finding and pruning ordinary PHI spans. Project code normalizes
pyDeid output and applies selected post-pyDeid replacement policies when raw
pyDeid behavior is not sufficient for longitudinal consistency or semantic
preservation. Stable patient-name and stable provider-name modes have bounded
exceptions: supplied aliases can be exact-matched after pyDeid so aliases
pruned by pyDeid can still receive stable identities. Provider single-token
aliases require provider-role context.

## Module Layout

- `src/project_phi/models.py`: `PHISpan` and `DeidentificationResult`.
- `src/project_phi/note.py`: public `deidentify_note(...)` orchestrator.
- `src/project_phi/csv_adapter.py`: public `deidentify_csv(...)` row adapter.
- `src/project_phi/pydeid_client.py`: pyDeid import and `deid_string(...)`
  boundary.
- `src/project_phi/normalization.py`: pyDeid surrogate records to `PHISpan`.
- `src/project_phi/reconstruction.py`: original-offset reconstruction when
  project replacements or vetoes are active.
- `src/project_phi/date_shift.py`: date-shift secret resolution, deterministic
  HMAC offset, and span-local date classifiers/parsers.
- `src/project_phi/patient_names.py`: explicit alias handling, bounded residual
  alias span creation, and stable fake patient identity generation.
- `src/project_phi/provider_names.py`: explicit provider-alias handling,
  provider-role context checks, bounded residual provider-alias span creation,
  and stable fake provider identity generation.
- `src/project_phi/protected_terms.py`: span-local protected clinical
  terminology false-positive vetoes, including exact whole-span terms and
  context-bound components inside approved clinical phrases.
- `src/project_phi/title_context.py`: narrow title-token-fragment and
  title-context action-word false-positive vetoes for pyDeid-emitted name spans.
- `src/project_phi/custom_regex.py`: project config to pyDeid `CustomRegex`
  conversion.
- `src/project_phi/audit.py`: audit column order, span rows, and sanitized
  warning rows.
- `src/project_phi/config_loaders.py`: patient/provider alias manifest CSV,
  custom regex JSON, and protected clinical terms CSV loaders.
- `src/project_phi/cli.py`: minimal command-line wrapper around
  `deidentify_csv(...)`.
- `src/project_phi/__init__.py`: public imports.

## pyDeid Boundary

`deidentify_note(...)` calls `run_pydeid_deid_string(...)`, which wraps pyDeid
`deid_string(...)`. pyDeid returns surrogate records and pyDeid's own
de-identified string. The wrapper normalizes those surrogate records. It does
not redo pyDeid detection or pruning for general PHI. When stable patient-name
or stable provider-name surrogates are enabled, it may add synthetic residual
spans for exact matches to supplied aliases. Provider single-token residual
matches are limited to provider-role context.

Surrogate records are pyDeid's table-like PHI records from `deid_string(...)`
output. 

The project uses pyDeid's internal regexes, dictionaries, wordlists, gazetteers,
custom regex matching, custom name-list handling, date/time detection, and
overlap pruning only through pyDeid runtime behavior.

## Orchestration Layers

`deidentify_note(...)` is the single-note unit of work. It validates project
options, builds pyDeid custom regex/name-list config, calls pyDeid, normalizes
spans, and optionally reconstructs final text.

`deidentify_csv(...)` is a row adapter around `deidentify_note(...)`. 

The CLI and config loaders are usability layers. They convert files and flags
into the same arguments accepted by `deidentify_csv(...)`.

## Offset Systems

The code intentionally keeps three offset systems separate:

- `PHISpan.start` / `PHISpan.end`: offsets into the original note.
- `metadata["pydeid_surrogate_start"]` /
  `metadata["pydeid_surrogate_end"]`: offsets in pyDeid's de-identified text.
- `metadata["project_replacement_start"]` /
  `metadata["project_replacement_end"]`: offsets in the project-final text
  when reconstruction is used.
