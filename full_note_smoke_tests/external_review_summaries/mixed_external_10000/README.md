# 10000-Row Mixed External Smoke-Review Summary

This folder contains public summary artifacts from a 10000-row external
ProjectPHI smoke set assembled from TCGA pathology reports and NCBI
Open-Patients examples.

The raw note/report bodies, de-identified outputs, full audit outputs,
issue-candidate tables, row-review tables, failure diagnostics, and chunk input
CSVs are intentionally excluded.

## Included Files

- `selection_summary.csv`: selected counts by source group, note type,
  breast-relevance flag, synthetic flag, chunk composition, and access notes.
- `source_manifest.csv`: source, URL, license/access, note-type, and selection
  metadata for each selected row.
- `chunk_01_manual_review.md` through `chunk_05_manual_review.md`: dated manual
  smoke-review summaries for the five 2000-row chunk runs.

## Source Composition

| Source group | Count |
| --- | ---: |
| Open-Patients breast/cancer filtered | 1500 |
| Open-Patients general medical | 1500 |
| Open-Patients reserve fill | 4043 |
| TCGA BRCA pathology | 1207 |
| TCGA non-BRCA pathology | 1750 |

Each chunk contains exactly 2000 rows with near-identical source composition.

## Review Method

The chunk smoke tests were run using Codex with GPT-5.5. Potential issues
identified by the coding agent were checked manually before source-code changes
were considered. These are smoke reviews without gold labels.

## Staleness Note

The included chunk reviews are dated snapshots from the last local chunk runs.
Some issue groups identified during chunk review were addressed in later
unit-tested ProjectPHI changes, including bounded semantic-preservation guards
for selected clinical phrases, abbreviations, source-ID/UUID-like artifacts,
vendor/device terms, and pathology/report terminology. Because the chunks were
not fully rerun after every later fix, the included manual reviews should be
read as dated review snapshots rather than final current-state issue counts.
The summaries remain useful for broad issue-profile documentation, but the
chunks should be rerun before citing final current performance metrics.

## Source And License Notes

The manifests record source URLs and license/access notes available when the
local smoke set was built. Users should review the upstream dataset cards,
repositories, and access terms before rebuilding or redistributing note/report
text.

Sources represented:

- TCGA-Reports: https://github.com/tatonetti-lab/tcga-path-reports
- NCBI Open-Patients: https://huggingface.co/datasets/ncbi/Open-Patients

Sources inspected but not included in this build:

- NCI ML Ready Pathology Reports
- RADSet BI-RADS
- Swiss-Mammo
- Kaggle Portuguese mammography synthetic dataset
