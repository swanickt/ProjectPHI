# Manual Review: External 10k Eval Chunk 4

Date generated: 2026-06-09

## Scope And Method

Ran the current ProjectPHI CLI against the local 2000-row chunk 04 input file
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
spans_written=3137
warnings=5
```

Input/output metadata matched for all 2000 rows. No output rows were empty.
1406 rows were text-identical to input, and 594 rows changed through
de-identification or date shifting.

Audit span labels: `NAME` 1447, `DATE` 1442, `TIME` 160, `LOCATION` 59,
`HOSPITAL` 25, `ID` 2, `CONTACT` 2, plus 5 warning rows.

Replacement sources: `pyDeid` 965, `project_stable_date_shift` 845,
`preserved` 757, `project_protected_clinical_term` 321,
`project_clinical_code_veto` 134, `project_ordinary_token_veto` 52,
`project_ordinary_clinical_prose_veto` 38,
`project_clinical_abbreviation_veto` 18,
`project_title_context_action_word_veto` 6,
`project_obstetric_history_veto` 1, plus 5 warning rows.

Row review statuses: 1034 unchanged with no candidate flags, 539
mitigated-only, and 427 review candidates present.

## Warnings

Five sanitized non-fatal row warnings were emitted:

- `tcga-923`
- `tcga-1089` twice
- `pmc-4888147-1`
- `pmc-3504539-1`

All five rows have de-identified output. Manual inspection showed ordinary
date shifting and pyDeid replacements in source, institution, or report-template
regions rather than row loss or output corruption.

## PHI And Formatting Review

No obvious residual email, dotted-phone, or adjacent `<PHI>`-surrogate pattern
was found.

Two output-pattern hits remain:

- `tcga-4656`: `https://clinapn8.duf.` is present as a malformed public/source
  URL-like fragment.
- `tcga-1113`: `833-434-9338` was introduced by pyDeid when replacing the
  input string `253888888-2544` in a citation/source-like context:
  `Clin Cancer Res. 2006; 12(8):253888888-2544. CRC.`

No confirmed PHI miss was identified. The dashed-phone hit is better classified
as a formatting/semantic artifact from pyDeid replacement, not a patient phone
number left behind.

## Current Review Candidates

There are 970 medium-priority precision/deferred candidates, plus five non-fatal
warnings, one low-priority URL-like output pattern, and one high-priority
contact-pattern heuristic hit. The contact-pattern hit is not a confirmed PHI
miss after input/output inspection.

Main groups:

- Location, institution, care-site, or source metadata: 296 candidates.
  Examples include `China`, `France`, `India`, `York`, `Somerville`,
  `Marlborough`, `Fremont`, `Shanghai`, `Abbott Park`, `Boston`, `Baltimore`,
  `de`, `HRH`, `LEIA`, and `XX`. These are intentionally deferred unless
  governed local policy supports preserving source or site metadata.
- Clinical or pathology precision candidates: 221 candidates. Examples include
  `Elston`, `frozen`, `SILVERBERG`, `Steiner`, `Statu`, `EBV-encoded`,
  `MAGEE`, `Kovacs`, `Lett`, `Edmondson`, `BENION`, `Permanent.`, `Wilm`,
  and `Leishman`. Many occur in report templates, citation fragments, OCR-like
  text, or classification/stain contexts. Some may be worth future
  phrase-bound rules if they recur in breast oncology notes.
- Short-fragment precision candidates: 208 candidates. Examples include
  `LEIA`, `at`, `p`, `XX`, `in`, `The`, `I`, `B.`, `DIEP`, `DARO`, `p.`,
  `ow`, `has`, and `n.`. Many are OCR/source-template fragments or provider
  placeholders. `DIEP` may be breast-reconstruction relevant, but should be
  guarded by procedure context rather than globally preserved.
- General precision candidates: 183 candidates. Examples include `Sarita`,
  `lait`, `DePuy`, `escalated`, `Johnson`, `Noonan`, `Smith`, `Ryles`,
  `Kulzer`, `Bracco`, `BioMerieux`, and `l'Etoile`. This bucket mixes source
  metadata, author-like names, device/vendor terms, and phrase fragments.
- Vendor, device, or reference metadata: 57 candidates. Examples include
  `DePuy` in limb-preservation system context, `Thora` in `Thora-Vent`,
  `Judkins` catheter, `Jackson`/`Pratt` in `Jackson Pratt (JP) drain`,
  `Tuohy` needle, `Harrington` rod, `Kerr`, `Hain`, `Teleflex`, `Medtronic`,
  and `Boston`. Some are plausible future context-bound preserves; none look
  urgent enough to broaden globally.

## Representative Input/Output Checks

- `Clin Cancer Res. 2006; 12(8):253888888-2544. CRC.` became
  `Clin Cancer Res. 2006; 12(8):833-434-9338. CRC.`
- `https://clinapn8.duf.` remained visible as a malformed source URL-like
  fragment.
- `Elston` was replaced in grading/classification contexts.
- `frozen` was replaced in frozen-section/report-template contexts.
- `EBV-encoded` was partly replaced in stain/probe contexts.
- `DIEP` was replaced in short-fragment contexts.
- `DePuy` was replaced in limb-preservation system context.
- `Thora` was replaced in `Thora-Vent` device context.
- `Judkins` was replaced in catheter context.
- `Jackson Pratt (JP) drain` was partly replaced because the current guard
  covers related variants but not this exact spaced parenthetical form.

## Mitigations Observed

Project semantic-preservation policies accounted for 2172 candidate rows:

- 845 stable date shifts
- 757 already-preserved date/time/year/score values
- 321 protected clinical terms
- 134 clinical-code or vendor/reference vetoes
- 52 ordinary-token vetoes
- 38 ordinary clinical prose vetoes
- 18 clinical abbreviation vetoes
- 6 title-context action-word vetoes
- 1 obstetric-history shorthand veto

## Follow-Up Items

1. Keep geography, institutions, care sites, source locations, and
   author/source-like metadata as pyDeid fallback unless governed local policy
   supports preserving them.
2. Do not treat the `tcga-1113` dashed-phone-like output as a PHI miss, but
   consider a future formatting guard if pyDeid repeatedly turns citation/page
   artifacts into phone-shaped surrogates.
3. Consider narrow future guards for recurrent clinical/device terms only when
   phrase or nearby context is strong, especially `Jackson Pratt (JP) drain`,
   `DIEP`, `Judkins`, `DePuy`, `Thora-Vent`, `Tuohy`, `Leishman`,
   `Elston SBR`, and frozen-section labels.
4. Continue avoiding global preservation for short fragments such as `at`,
   `p`, `XX`, `I`, `B.`, `The`, and similar tokens.
