# Manual Review: 10000-Note Eval Chunk 03

Date regenerated: 2026-06-09

## Scope And Method

Reran the current ProjectPHI CLI against the local 2000-row chunk 03 input
file after the latest genomic/source-ID and bounded semantic-preservation
guards.

Regenerated only this run folder's `deidentified_output.csv`,
`audit_output.csv`, `audit_summary.csv`, `issue_candidates.csv`,
`row_review_summary.csv`, `failure_diagnostics.csv`, and this review.

The review compared parsed input rows, output rows, audit rows, warning rows,
source-group counts, changed/unchanged text, residual contact-like output
patterns, and pyDeid fallback replacements. It is a smoke review without gold
labels.

## Pipeline Summary

```text
rows_read=2000
rows_written=2000
rows_failed=0
spans_written=3233
warnings=9
```

Input/output row IDs and source-group counts matched for all 2000 rows. No
output row had empty `note_text`.

Among written rows, 1355 were text-identical to input and 645 changed through
de-identification, date shifting, or semantic-preservation reconstruction.

Audit span labels:

- `NAME`: 1581
- `DATE`: 1347
- `TIME`: 214
- `LOCATION`: 44
- `HOSPITAL`: 41
- row warning records: 9
- `ID`: 3
- `CONTACT`: 3

Replacement sources:

- `pyDeid`: 1074
- `project_stable_date_shift`: 843
- `preserved`: 718
- `project_protected_clinical_term`: 322
- `project_clinical_code_veto`: 144
- `project_ordinary_token_veto`: 59
- `project_ordinary_clinical_prose_veto`: 36
- `project_clinical_abbreviation_veto`: 29
- row warning records: 9
- `project_title_context_action_word_veto`: 7
- `project_obstetric_history_veto`: 1

Row review statuses:

- 1031 unchanged with no candidate flags
- 492 mitigated-only
- 477 review candidates present
- 0 failed

## Changes Since Prior Chunk-3 Review

The prior report described one failed row, `pmc-4696335-1`, from overlapping
pyDeid spans inside genomic coordinate ranges. That row now writes output. The
remaining nine warnings all come from this same row and represent overlap
pruning telemetry rather than row failure.

Direct audit counts improved compared with the stale failed-row report:

- rows written increased from 1999 to 2000.
- failed rows dropped from 1 to 0.
- pyDeid fallback spans dropped from 1172 to 1074.
- protected clinical-term mitigations increased from 276 to 322.
- clinical-code/vendor/contextual mitigations increased from 98 to 144.
- total mitigated candidates increased from 2054 to 2159.

## PHI-Miss And Formatting Review

No residual email, dashed-phone, dotted-phone, or adjacent `<PHI> <PHI>`
pattern was found in `deidentified_output.csv`.

Three URL-like public-source strings remain:

- `www.umd.be/HSF3/index.html,` in `pmc-6421267-1`
- `www.graphpad.com)` in `pmc-7903284-1`
- `https://vpn.chgi.ucalgary.ca/),` in `pmc-6388456-1`

These are public source/tool metadata, not confirmed patient PHI misses.

No confirmed residual PHI miss was identified in this rerun.

## Current Review Candidates

There are 1083 non-mitigated review candidates in the conservative heuristic
scan:

- 9 medium pipeline warnings from overlap-pruned spans in a row that still
  wrote successfully.
- 3 low-priority public-source URL/tool artifacts.
- 1074 pyDeid fallback spans where replacement may remove source meaning.

The 1074 pyDeid fallback spans break down heuristically as:

- 323 deferred location, institution, care-site, manufacturer-location, or
  source metadata candidates.
- 265 clinical/pathology precision candidates.
- 229 other precision candidates.
- 213 short-fragment candidates.
- 44 vendor/device precision candidates.

These buckets intentionally over-call review candidates. They are designed to
surface places where pyDeid changed text, not to assert that every replacement
is a bug.

## Issue Groups

### 1. Pipeline Warnings

Nine sanitized warnings were emitted, all in `pmc-4696335-1`.

This row is a public genetics case with many genomic coordinate ranges. It now
writes output successfully. The warnings reflect deterministic pruning of
overlapping pyDeid spans inside complex coordinate text.

Suggested handling: keep tracking. No immediate functional change is needed
unless warning rows begin showing malformed output or the warning count grows.

### 2. Public-Source URL/Tool Metadata

Three URL-like strings remain in output, all public tool/source metadata.

Suggested handling: do not fix as PHI. If public-source URLs are distracting in
reports, they could be listed separately from PHI-miss checks.

### 3. Deferred Location, Institution, Care-Site, And Source Metadata

Examples include `de`, `LA`, `France`, `China`, `Paulo`, `India`, `Fremont`,
`York`, `Paris`, `Somerville`, `Milan`, `Lanka`, `Navarra`, `Beijing`,
`Soetomo`, `Marcy`, `King`, `Abdullah`, plus source/citation names such as
`Burstein`, `Carlson`, `Anderson`, `JN`, and `RW`.

Suggested handling: do not add broad built-in preservation. These can be true
site, geography, manufacturer-location, source/citation, or institution
identifiers in real notes. Preserve only through governed local policy or very
specific phrase/context rules.

### 4. Clinical Or Pathology Precision Candidates

Examples include `Elston`, `Comment`, `frozen`, `INTRA`, `OPERATIVE`,
`Compliance`, `validated`, `Stain`, `Hilden`, `Pico`, `Ferriman`, `Booker`,
`Knott`, and citation/source names in breast HER2 reference boilerplate.

Many are report-template fragments, OCR/source damage, or citation names. Some
are clinically useful but require stronger bounded context.

Suggested handling: no broad preserve. Potential future narrow candidates are
additional `Elston SBR grade` variants, `frozen`/`INTRA OPERATIVE` in
frozen-section context, and selected eponyms if they recur in breast-relevant
notes. Skip OCR typo guards unless a specific typo recurs enough to matter.

### 5. Short Fragments And OCR/Template Tokens

Examples include `p`, `JI`, `HIER`, `dr`, `and`, `B`, `Foi`, `Pathol`,
`mammoplasty`, `PASH`, `SBR`, `OCT`, `SNB`, and similar fragments.

Some are valid clinical/report abbreviations, some are source-template
fragments, and some are ordinary words or OCR damage.

Suggested handling: fix only recurring high-value clinical abbreviations with
strong context. `PASH`, `SBR`, `HIER`, `OCT`, and `SNB` may be reasonable
future context-bound candidates if they recur. Do not preserve short tokens
globally.

### 6. Vendor, Device, And Manufacturer Metadata

Examples include `Mega`, `Perkin`, `Elmer`, `Picard`, `Hain`, `Anton`,
`Paar`, `LaCAR`, `Ribogreen`, `LabChip`, `Judkins`, `DePuy`, `Beckman`,
`Hilden`, `Fogarty`, and manufacturer/source locations such as `Besancon`.

Suggested handling: preserve only when product-specific context is strong.
Reasonable future candidates include `Micro Mega`, `Perkin Elmer`,
`Picard Tools`, `Hain Lifescience`, `Anton Paar`, `RiboGreen`, `LabChip`,
`Judkins` catheter, and `DePuy` implant contexts. Manufacturer locations
should stay deferred.

### 7. Other Precision Candidates

Examples include `Limberg`, `Sereno`, `Smith`, `Zhang`, `Italia`, `Merial`,
`Bracco`, `Fischl`, `Burch`, `Basel`, `Seiler`, `Edwards`, `Stice`, `nass`,
`vere`, `Stam`, and OCR/source-template fragments.

Suggested handling: this remains mixed. Some terms may be future phrase-bound
clinical or product candidates if they recur. Many are names, public-source
metadata, geography, or OCR/source-template damage and should remain pyDeid
fallback.

## Mitigations Observed

Project semantic-preservation policies accounted for 2159 mitigated candidate
rows:

- 843 stable date shifts
- 718 preserved date/time/year/score values
- 322 protected clinical terms
- 144 clinical-code/vendor/contextual vetoes
- 59 ordinary-token vetoes
- 36 ordinary clinical prose vetoes
- 29 clinical-abbreviation vetoes
- 7 title-context action-word vetoes
- 1 obstetric-history shorthand veto

## Follow-Up Items

1. Keep geography, institutions, care sites, manufacturer locations,
   source/citation names, and short ambiguous tokens as pyDeid fallback unless
   governed local policy says otherwise.
2. Consider future narrow guards only for recurrent high-value clinical terms
   such as `PASH`, `SBR`, `HIER`, `SNB`, `Elston SBR grade`, and
   frozen-section/intraoperative wording.
3. Consider product-specific vendor guards only where device or assay context
   is strong, such as `Micro Mega`, `Perkin Elmer`, `Picard Tools`,
   `Hain Lifescience`, `Anton Paar`, `RiboGreen`, `LabChip`, `Judkins`, and
   `DePuy`.
4. Keep OCR typo fixes deprioritized unless a specific typo repeats in real
   breast/pathology notes and materially affects downstream extraction.
