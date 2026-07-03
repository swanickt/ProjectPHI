# Manual Review: 10000-Note Eval Chunk 01

Date regenerated: 2026-06-09

## Scope And Method

Reran the current ProjectPHI CLI against the local 2000-row chunk 01 input
file after the latest bounded pathology/classification, abbreviation, and
vendor/device semantic-preservation guards.

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
spans_written=2829
warnings=5
```

Input/output row IDs and source-group counts matched for all 2000 rows. No
output row had empty `note_text`.

Among written rows, 1410 were text-identical to input and 590 changed through
de-identification, date shifting, or semantic-preservation reconstruction.

Audit span labels:

- `NAME`: 1328
- `DATE`: 1239
- `TIME`: 171
- `LOCATION`: 48
- `HOSPITAL`: 40
- `CONTACT`: 3
- row warning records: 5

Replacement sources:

- `pyDeid`: 876
- `preserved`: 716
- `project_stable_date_shift`: 694
- `project_protected_clinical_term`: 229
- `project_clinical_code_veto`: 163
- `project_ordinary_token_veto`: 64
- `project_ordinary_clinical_prose_veto`: 45
- `project_clinical_abbreviation_veto`: 32
- `project_title_context_action_word_veto`: 7
- row warning records: 5
- `project_decimal_code_veto`: 2
- `project_obstetric_history_veto`: 1

Row review statuses:

- 1045 unchanged with no candidate flags
- 521 mitigated-only
- 434 review candidates present
- 0 failed

## Changes Since Prior Chunk-1 Review

The previous high-priority issues remain resolved:

- The two formerly failed rows still write output:
  - `tcga-5904`
  - `pmc-6099003-1`
- The genomic coordinate ranges in `pmc-6099003-1`, including examples such
  as `154559773-171639287`, are preserved in bounded cytogenetic context.
- Day-month-year comma dates shift rather than falling back to `<DATE>`.
- Long floating-point tumor-size values are not converted into phone-like
  pyDeid surrogates.

The latest bounded-guard pass further improved the chunk:

- pyDeid fallback spans dropped from 909 to 876.
- Protected clinical-term mitigations increased from 217 to 229.
- Clinical-code/vendor/contextual mitigations increased from 142 to 163.
- Total mitigated candidates increased from 1920 to 1953.

Newly observed mitigations include bounded guards for examples such as
`Lauren class`, `Ishak fibrosis`, `Elston` grading contexts, `Edmondson` grade
or classification contexts, `von Kossa` stains, `Fowler-Stephen` orchiopexy,
`BEV` near bevacizumab/chemotherapy context, `DES` near desmin pathology
context, `TPC`/`TPD`/`TPF` in touch-prep/frozen-section report context, `Carl`
in Carl Zeiss contexts, and product/device contexts for `SALSA`, `Guidant`,
and `Ethicon`.

## PHI-Miss Review

No residual email, dashed-phone, dotted-phone, or adjacent `<PHI> <PHI>`
pattern was found in `deidentified_output.csv`.

Two malformed URL-like strings remain:

- `https://.` in `tcga-7675`
- `https://.` in `tcga-5842`

These strings were already present in the public source text and are treated as
source artifacts, not confirmed PHI misses.

No confirmed residual PHI miss was identified in this rerun.

## Current Review Candidates

There are 881 non-mitigated review candidates in the conservative heuristic
scan:

- 5 medium pipeline warnings from overlap-pruned spans in rows that still wrote
  successfully.
- 2 low-priority malformed public-source URL artifacts.
- 876 pyDeid fallback spans where replacement may remove source meaning.

The 876 pyDeid fallback spans break down heuristically as:

- 271 deferred location, institution, care-site, manufacturer-location, or
  source metadata candidates.
- 209 short-fragment candidates.
- 198 clinical/pathology precision candidates.
- 24 vendor/device precision candidates.
- 174 other precision candidates.

These buckets intentionally over-call review candidates. They are designed to
surface places where pyDeid changed text, not to assert that every replacement
is a bug.

## Issue Groups

### 1. Pipeline Warnings

Five sanitized warnings were emitted:

- one in `tcga-5904`
- four in `pmc-6099003-1`

Both rows wrote output. The warnings are related to overlap-pruned pyDeid spans
in complex text; the previously failing genomic-coordinate row remains
recoverable. These are medium-priority telemetry issues, not row failures.

Suggested handling: keep tracking in smoke reports. Do not change behavior
unless warnings increase or a warning row shows malformed output.

### 2. Malformed Public-Source URL Artifacts

The output still contains `https://.` in two TCGA reports. The same malformed
string is present in the input.

Suggested handling: ignore for ProjectPHI semantics. This is a public-source
artifact, not residual patient contact information.

### 3. Deferred Location, Institution, Care-Site, And Source Metadata

Examples include `LA`, `India`, `Marlborough`, `China`, `Seefeld`, `Naples`,
`Somerville`, `Paulo`, `Lanka`, `German`, `Delhi`, `Lucia`, `Lafayette`, and
source/institution-like phrases. Some ordinary tokens are also pulled into
this bucket when they appear near provider, institution, or source-template
language.

Suggested handling: do not add broad built-in preservation. These strings can
be true site, geography, manufacturer-location, or institution identifiers in
real notes. Preserve only through governed local policy or highly bounded
product/source context.

### 4. Short Fragments And OCR/Template Tokens

Examples include `The`, `at`, `A`, `B`, `p`, `EBER`, `KAPA`, `EMA`, `DIEP`,
`DAIR`, `ANNA`, `BAFF`, `VER`, `ID`, `SHON`, and similar fragments. Many occur
in TCGA/OCR-like report templates, author/signature remnants, section lists,
or abbreviations.

Suggested handling: fix only recurring, clinically meaningful fragments with
strong context. Do not globally preserve short tokens because they overlap with
initials, names, locations, and arbitrary OCR damage.

### 5. Clinical Or Pathology Precision Candidates

Examples include `Grocott`, `Elston`, `Coller`, `Langhans`, `Guyon`, `left`,
`frozen`, `stich`, `Attending`, `Pathologist`, `Specimen`, `tumor`, and
source-template/OCR fragments such as `Engl`, `OPPER`, `whtie`, and
`Microscopia`.

The latest fixes removed several higher-confidence classification and stain
contexts, but some variants still lack enough bounded context for preservation
or look like OCR/source-template damage.

Suggested handling: continue adding only narrow phrase-bound guards for
recurrent clinically useful terms. Do not preserve broad ordinary words such
as `left`, `tumor`, or `Specimen` globally.

### 6. Vendor, Device, And Manufacturer Metadata

Examples include `Judkins`, `FeNO`, `Kapa`, `Jason`, `Rosch`, `Biel`, `Huber`,
`Rusch`, and manufacturer-location strings such as `Sommerville`.

The latest product-context guards reduced this group from 36 to 24 candidates.

Suggested handling: preserve only when product-specific context is strong.
Manufacturer locations and person-like product names should remain deferred
unless a governed local policy or very specific product phrase supports them.

### 7. Other Precision Candidates

Examples include `Biel`, `Bayer`, `shorthair`, `colli`, `Winter`, `Smith`,
`Mueller`, `Hinton`, `Sert`, `Monti`, `CONFIDENTIAL`, `Encounte`, `apex`, and
OCR/source words such as `belew`, `celi`, `bleck`, or `teets`.

Suggested handling: this remains a mixed bucket. Some terms may be future
phrase-bound candidates if they recur and are clinically useful. Others are
names, public-source metadata, manufacturer locations, or OCR/source-template
damage and should remain pyDeid fallback.

## Mitigations Observed

Project semantic-preservation policies accounted for 1953 mitigated candidate
rows:

- 716 preserved date/time/year/score values
- 694 stable date shifts
- 229 protected clinical terms
- 163 clinical-code/vendor/contextual vetoes
- 64 ordinary-token vetoes
- 45 ordinary clinical prose vetoes
- 32 clinical-abbreviation vetoes
- 7 title-context action-word vetoes
- 2 decimal-code/long-float contact vetoes
- 1 obstetric-history shorthand veto

## Follow-Up Items

1. Keep geography, institutions, care sites, manufacturer locations, and
   source-location metadata as pyDeid fallback unless governed local policy
   says otherwise.
2. Treat remaining short fragments as low-value unless they recur in real
   breast oncology notes with clear phrase-bound or context-bound clinical
   meaning.
3. Consider future narrow guards only for recurrent breast/pathology-specific
   residuals with strong context. Avoid OCR typo guards unless the same typo
   recurs enough to matter.
4. Review remaining vendor/device metadata cautiously. Preserve only when
   product-specific context is strong enough to avoid preserving real person,
   institution, or location names.
