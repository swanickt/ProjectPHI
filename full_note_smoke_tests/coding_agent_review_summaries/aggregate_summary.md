# Aggregate External Smoke-Review Summary

This file summarizes the public review artifacts in this folder. Raw note text,
de-identified outputs, full audit tables, row-level issue-candidate tables, and
chunk input CSVs are intentionally excluded.

## Review Method

The smoke tests were run using Codex with GPT-5.5. Potential issues identified
by the coding agent were checked manually before source-code changes were
considered. The resulting files are smoke-review summaries, not gold-standard
evaluation labels.

## 1000-Note Open-Patients Review

Source: NCBI Open-Patients on Hugging Face.

Rows reviewed: 1000.

Source composition:

| Source group | Count |
| --- | ---: |
| TREC CDS 2014 | 30 |
| TREC CDS 2015 | 30 |
| TREC CDS 2016 | 30 |
| TREC CT 2021 | 75 |
| TREC CT 2022 | 50 |
| PMC-Patients | 450 |
| USMLE-style cases | 335 |

Latest included manual-review snapshot: 2026-06-09.

High-level result from the included review:

- 1000 rows read and written.
- 0 failed rows.
- 907 spans written.
- 0 warnings.
- 0 confirmed PHI misses in the manual smoke review.
- 48 remaining medium-priority review candidates, mostly deferred geography,
  institution/care-site metadata, and short fragments.

## 10000-Row Mixed External Review

Sources: TCGA pathology reports and NCBI Open-Patients.

Rows selected: 10000.

Source composition:

| Source group | Count |
| --- | ---: |
| Open-Patients breast/cancer filtered | 1500 |
| Open-Patients general medical | 1500 |
| Open-Patients reserve fill | 4043 |
| TCGA BRCA pathology | 1207 |
| TCGA non-BRCA pathology | 1750 |

The 10000-row set was reviewed as five source-stratified 2000-row chunks. The
full 10000-row CLI run was not run in the local source folder.

Chunk review snapshots:

| Chunk | Rows read | Rows written | Failed rows | Spans written | Warnings |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 2000 | 2000 | 0 | 2829 | 5 |
| 2 | 2000 | 2000 | 0 | 3111 | 2 |
| 3 | 2000 | 2000 | 0 | 3233 | 9 |
| 4 | 2000 | 2000 | 0 | 3137 | 5 |
| 5 | 2000 | 2000 | 0 | 3188 | 4 |

Latest included chunk-review snapshots: 2026-06-09.

Important context:

- The chunk run folders reflected the ProjectPHI pipeline state at the time each
  chunk was last rerun.
- Some issue groups identified during chunk review were addressed in later
  unit-tested ProjectPHI changes, including bounded semantic-preservation
  guards for selected clinical phrases, abbreviations, source-ID/UUID-like
  artifacts, vendor/device terms, and pathology/report terminology. Because the
  chunks were not fully rerun after every later fix, the included manual
  reviews should be read as dated review snapshots rather than final
  current-state issue counts.
- The reviews remain useful for broad issue-profile documentation, but they
  should not be cited as final current-performance metrics without rerunning the
  chunks.

## Recommended Interpretation

These reviews support public discussion of how ProjectPHI was stress-tested over
larger public clinical-text resources. They should not be used as certification
that ProjectPHI output is PHI-free, externally releasable, or complete for all
Ontario clinical settings.
