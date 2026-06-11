# pyDeid Behavior Used By ProjectPHI

This page documents what ProjectPHI inherits from pyDeid. 

## Detection, Pruning, And Base Replacement

ProjectPHI delegates PHI detection, overlap pruning, and initial surrogate
replacement to pyDeid through `deid_string(...)`. The local boundary is
`src/project_phi/pydeid_client.py`, called by `src/project_phi/note.py`.

The wrapper relies on pyDeid for:

- built-in regex/list PHI detection;
- overlap pruning;
- base pyDeid surrogate generation;
- date/time span detection;
- name, address, location, hospital, contact, MRN/OHIP/SIN, and related
  pyDeid-supported PHI categories at the level exposed by pyDeid;
- custom regex matching when configured;
- custom doctor/patient name-list handling when configured.

## `deid_string(...)` Parameters Used By The Wrapper

The local pyDeid source exposes `deid_string(...)` for single-note strings with
parameters including:

- `note`;
- `custom_dr_first_names`;
- `custom_dr_last_names`;
- `custom_patient_first_names`;
- `custom_patient_last_names`;
- `named_entity_recognition`;
- `two_digit_threshold`;
- `valid_year_low`;
- `valid_year_high`;
- `types`;
- `**custom_regexes`.

ProjectPHI currently passes through the custom doctor/patient name sets,
including provider aliases merged into pyDeid doctor-name lists when stable
provider-name surrogates are enabled. It also passes `types` and pyDeid custom
regex objects. It always calls pyDeid with `named_entity_recognition=False`.
The pyDeid date-year threshold parameters are left at pyDeid defaults because
the public wrapper does not currently expose them.

The default pyDeid `types` requested by the wrapper are:

```python
["names", "dates", "sin", "ohip", "mrn", "locations", "hospitals", "contact"]
```

## Surrogate Records

The local pyDeid call returns a tuple equivalent to:

```python
surrogates, deidentified_text = deid_string(note, ...)
```

`surrogates` is a table-like collection of pyDeid PHI records. A surrogate
record commonly includes:

- `phi_start` and `phi_end`: original-note offsets;
- `phi`: the detected original value, sometimes a pyDeid date/time namedtuple;
- `surrogate_start` and `surrogate_end`: offsets in pyDeid's de-identified
  string;
- `surrogate`: pyDeid replacement text;
- `types`: pyDeid type strings.

ProjectPHI normalizes each surrogate record into one `PHISpan`. 

## Wordlists And Gazetteers

pyDeid has internal wordlists/gazetteers, including common-word and medical
resources. ProjectPHI relies on those resources only through normal pyDeid
runtime behavior. The project does not copy them into its own resources.


## Detection Wordlists vs Replacement Surrogates

pyDeid wordlists and pyDeid surrogate generation serve different purposes.

The wordlists are primarily detection and false-positive-control resources.
For name handling, pyDeid loads first-name, last-name, doctor-name, ambiguous
name, common-word, and related resources so it can decide whether a token should
be flagged as a name-like PHI span. Similar internal resources support other
categories such as locations, hospitals, common words, and medical terminology.

Replacement happens later. Once pyDeid has decided a span is PHI, its replacer
chooses surrogate text. In the local pyDeid source, name replacement uses the
Python `Faker` library rather than selecting directly from the detection
wordlists:

```python
self.fake = Faker()
self.fake.first_name()
self.fake.last_name()
```

pyDeid also keeps an internal `name_lookup` during a single replacement run so
the same exact original name string can receive the same surrogate within that
run. That lookup is internal to one pyDeid replacement instance. It is not a
patient-keyed cross-note identity store.

This distinction matters for ProjectPHI:

- pyDeid wordlists help pyDeid find names; they are not treated by
  ProjectPHI as project surrogate-name pools.
- pyDeid/Faker name surrogates are useful default replacements, but they are
  not stable across notes for the same patient under the current public
  `deid_string(...)` integration.
- Stable patient-name and provider-name surrogates therefore use project-level
  deterministic Faker generation seeded from HMACs over configured IDs and
  runtime secrets, for pyDeid-detected spans that match explicit aliases and
  for bounded residual exact matches to supplied aliases that pyDeid pruned.
- Unknown names, clinician names, family names, and other non-matching names
  continue to use pyDeid's replacement behavior in single-note, CSV, and CLI
  workflows. The Python-only patient batch API can optionally stabilize
  remaining pyDeid-detected unknown names within one patient's supplied notes.

The exact generated fake names can depend on the installed Faker version and
provider data. The stable contract is that the same `patient_id`, secret, and
runtime environment produce the same project fake identity. Unknown names use
pyDeid's own replacement path unless the Python patient batch API explicitly
enables patient-local unknown-name surrogates.

## Custom Regexes

ProjectPHI accepts a project-shaped custom regex configuration and converts
it into pyDeid custom regex objects in `src/project_phi/custom_regex.py`.
pyDeid performs the actual matching and pruning. The project does not scan note
text with those regexes as a separate detector.

Project metadata records the project rule ID and configured PHI type for spans
that match configured custom regex types. Raw regex patterns are not copied into
span metadata, audit rows, warnings, or CLI output.

**Warning:** pyDeid also uses the custom regex `phi_type` during replacement. If the
configured type contains a built-in pyDeid replacement cue such as `MRN`,
`Name`, `Date`, `Time`, `Hospital`, `Telephone`, or `Email`, pyDeid may choose
that built-in surrogate style before it reaches the custom surrogate builder.
For constant custom replacements, use neutral type names and keep the
site-specific meaning in the project rule ID and governed configuration notes.

## Custom Name Lists

pyDeid supports custom patient/doctor first and last name lists. ProjectPHI
passes caller-provided lists through to pyDeid. When stable patient-name
surrogates are enabled, ProjectPHI also derives custom patient name tokens
from explicit aliases to improve pyDeid detection. When stable provider-name
surrogates are enabled, ProjectPHI derives custom doctor name tokens from
configured provider aliases.

Those name-list hooks can broaden pyDeid detection. Project-stable patient-name
and provider-name replacement applies to explicit alias policy only. If pyDeid
still misses or prunes a supplied alias, ProjectPHI can create a residual span
using bounded exact matching against that caller-supplied alias. Single-token
provider aliases require provider-role context. Unknown names remain pyDeid
replacements unless the Python patient batch API explicitly stabilizes
remaining unknown-name spans within one patient's supplied notes.

## Title-Context Name Heuristics

pyDeid title/name heuristics can label tokens after titles such as `Dr.` as
name spans. In some cases, clinical action words are emitted as title-derived
name spans, for example `examined` in `The Dr. examined the patient`,
`reviewed` in `Dr. Solen reviewed mammography`, or `Reviewed` in
`Dr. Reviewed mammography`.

ProjectPHI does not change pyDeid detection. It adds a narrow reconstruction
veto for pyDeid-emitted title-derived name spans when the token is a curated
clinical action word, appears in a narrow title or clinical-role context, is
not an explicit custom patient/provider alias, and is not present in pyDeid's
name lists. Lower-case action words use the base `Dr.` rule; capitalized action
words also require specific following clinical-object context or generic
patient/person context. This preserves common documentation verbs without
turning pyDeid common words into a broad PHI override. If pyDeid also emits the
adjacent clinical-object token as a title-derived name span, ProjectPHI can
preserve that token as part of the same bounded false-positive pattern.
ProjectPHI can also preserve a lower-case action word immediately after a
replaced role/title name span, while leaving the preceding name replacement
unchanged.

## pyDeid Replacement Preservation

When no project reconstruction is needed, ProjectPHI returns pyDeid's
de-identified text directly. When reconstruction is needed, non-date/non-name
spans and unknown names use pyDeid's replacement fallback unless another
project policy applies. The optional patient batch unknown-name registry is one
such policy and is not active for single-note, CSV, or CLI defaults.

pyDeid replacement text and pyDeid surrogate offsets are preserved in span
metadata so audit/debug workflows can distinguish pyDeid output from
project-final replacement output.

## NER

Although pyDeid has NER-related capabilities, this project rejects
`named_entity_recognition=True` and keeps NER out of the current baseline.
