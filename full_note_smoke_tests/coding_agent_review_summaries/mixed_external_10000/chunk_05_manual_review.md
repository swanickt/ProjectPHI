# Manual Review: External 10k Eval Chunk 5

Date generated: 2026-06-09

## Scope And Method

Reran the current ProjectPHI CLI against the local 2000-row chunk 05 input file
and wrote outputs into the local run folder only.

The review compared all input/output row pairs, audit metadata, warning rows,
residual contact-like output patterns, and representative contexts for each
candidate family. This remains a smoke review without gold labels.

## Chunk Composition

```text
open-patients-reserve-fill: 809
tcga-non-brca-pathology: 350
open-patients-breast-cancer-filtered: 300
open-patients-general-medical: 300
tcga-brca-pathology: 241
```

## Pipeline Summary

```text
rows_read=2000
rows_written=2000
rows_failed=0
spans_written=3188
warnings=4
```

Input/output metadata matched for all 2000 rows. No output rows were empty.
1381 rows were text-identical to input, and 619 rows changed through
de-identification or date shifting.

Audit span labels: `NAME` 1518, `DATE` 1360, `TIME` 215, `LOCATION` 56,
`HOSPITAL` 32, `CONTACT` 4, `ID` 3, plus 4 warning rows.

Replacement sources: `pyDeid` 1048, `project_stable_date_shift` 812,
`preserved` 763, `project_protected_clinical_term` 296,
`project_clinical_code_veto` 141, `project_ordinary_token_veto` 65,
`project_ordinary_clinical_prose_veto` 32,
`project_clinical_abbreviation_veto` 23,
`project_title_context_action_word_veto` 6, and
`project_decimal_code_veto` 2, plus 4 warning rows.

Row review statuses: 1030 unchanged with no candidate flags, 528
mitigated-only, and 442 review candidates present.

## Warnings

Four sanitized non-fatal row warnings were emitted:

- `tcga-8025`
- `tcga-206`
- `pmc-7251487-1`
- `pmc-7308141-1`

All four rows have de-identified output. Manual inspection showed ordinary
date shifting and pyDeid replacements in dense source, geography, template, or
OCR-heavy regions rather than row loss or output corruption.

## PHI And Formatting Review

No residual email or dotted-phone pattern was found.

High-priority output-pattern heuristics flagged 11 cases:

- Ten adjacent `<PHI>`/surrogate-name patterns. Manual inspection showed
  pyDeid replacements in source/geography/name-particle or term contexts, such
  as `torsade de pointes` becoming `torsade <PHI> Barry`,
  `en coup de sabre` becoming `en coup <PHI> Johnson`, and manufacturer or
  institution text such as `S.A. de C.V.` and French institution phrases being
  partly masked.
- One dashed-phone-shaped surrogate: `306-536-1466` was introduced by pyDeid
  when replacing the input bionumber `6760001000101` in a microbiology/Vitek
  ANI card context.

Low-priority URL-like output patterns were also observed:

- Five `https://.` fragments already present in TCGA pathology text.
- Three public/source URLs in Open-Patients notes:
  `http://www.brain.org.`,
  `http://chromas.software.informer.com/2.4/).`, and
  `http://blast.ncbi.nlm.nih.gov/Blast.cgi).`

No confirmed PHI miss was identified in this chunk review. The high-priority
hits are better classified as formatting or semantic-muddying artifacts from
pyDeid replacement, not patient contact information left in the output.

## Current Review Candidates

There are 1052 medium-priority precision/deferred candidates, plus 11
high-priority output-pattern heuristic hits and 8 low-priority URL-like output
patterns. The candidate counts are intentionally conservative and include many
OCR/source-template fragments.

Main groups:

- Clinical or pathology precision candidates: 557 candidates. Common examples
  include `at` / `to` in `Diagnosis called to Dr. at/by Dr.` templates,
  `concurs`, `GUSS`, `PASH`, `Elston`, `Carlson`, `Burstein`, `Statu`,
  `DIEP`, `Bormann`, `MOC`, and `GIA`. This bucket mixes real semantic-loss
  examples with provider-template and reference-list text.
- Location, institution, care-site, or source metadata: 182 candidates.
  Examples include `de`, `India`, `China`, `The Arthur G. James Cancer
  Hospital`, `York`, `Paulo`, `France`, `Hilden`, `Beijing`, `Somerville`,
  `Marlborough`, `Naples`, `Marcy`, and `Seefeld`. These remain intentionally
  deferred unless governed local policy supports preserving source/site
  metadata.
- General precision candidates: 162 candidates. Examples include `Ramadan`,
  `Di Donato`, `micro-Strout`, `Milan`, `3D Slicer`, `naso-pharyngeal`,
  `prescribed`, `cafe-au-lait`, `Alexis`, `Pfannenstiel`, `Sorensen`, and
  `diagnosed`. This group contains useful clinical/source meaning, but also
  author names, locations, devices, and ordinary words that are unsafe to
  preserve globally.
- Vendor, device, or reference metadata: 97 candidates. Examples include
  `Lugo`, `guider`, `Ramadan`, `Rastelli`, `Tustin`, `Tuohy`, `Kerr`, `Nuss`,
  `Cordis/Miami Lakes`, `DAIR`, and additional manufacturer/device contexts.
  Some are plausible future context-bound preserves; none should be global.
- Short-fragment precision candidates: 50 candidates. Examples include `D`,
  `and`, `BAE`, `ost`, `had`, `au`, `SMH`, `B.`, `ARY`, `la`, `Pri`, `cui`,
  and `wal`. Most are OCR/source-template fragments or ambiguous short tokens.

## Representative Input/Output Checks

- `torsade de pointes` became `torsade <PHI> Barry`.
- `scleroderma en coup de sabre` became `scleroderma en coup <PHI> Johnson`.
- `bionumber 6760001000101` became `bionumber 306-536-1466`.
- `PASH` was replaced in pseudoangiomatous stromal hyperplasia context.
- `Elston SBR grade 2` had `Elston` replaced.
- `DIEP` was replaced in short-fragment contexts.
- `Gugging Swallowing Screen (GUSS)` had `GUSS` replaced.
- `cafe-au-lait` had `au` / `lait` components replaced in some contexts.
- `Naranjo's algorithm score`-style and other reference/device score terms
  continue to require context-bound handling.
- `The Arthur G. James Cancer Hospital` was masked as site metadata, which is
  expected under the current governed-location policy.

## Mitigations Observed

Project semantic-preservation policies accounted for 2140 candidate rows:

- 812 stable date shifts
- 763 already-preserved date/time/year/score values
- 296 protected clinical terms
- 141 clinical-code or vendor/reference vetoes
- 65 ordinary-token vetoes
- 32 ordinary clinical prose vetoes
- 23 clinical abbreviation vetoes
- 6 title-context action-word vetoes
- 2 decimal-code/contact false-positive vetoes

## Follow-Up Items

1. Keep geography, institutions, care sites, source locations, manufacturer
   locations, and source-language name particles such as non-anatomic `de` as
   pyDeid fallback unless governed local policy supports preserving them.
2. Consider narrow phrase-bound clinical guards only for repeated,
   breast-relevant or generally useful terms such as `PASH`, `DIEP` in
   reconstruction context, `Elston SBR`, `GUSS`, `cafe-au-lait`,
   `GIA-75 stapler`, and `Naranjo's algorithm score`.
3. Consider a future formatting guard for pyDeid-generated phone-shaped
   surrogates in clear bionumber/citation/reference contexts if this repeats
   across more chunks.
4. Do not globally preserve short fragments such as `at`, `to`, `I`, `p`,
   `D`, `B.`, `The`, `and`, `au`, or `lait`; they need phrase/context bounds
   because many occur in provider templates, OCR noise, author names, or
   source text.
