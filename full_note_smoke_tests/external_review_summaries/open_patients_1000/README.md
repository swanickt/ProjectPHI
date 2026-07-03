# 1000-Note Open-Patients Smoke-Review Summary

This folder contains public summary artifacts from a 1000-note ProjectPHI smoke
review over selected NCBI Open-Patients examples.

The raw note bodies, de-identified output, full audit output, issue-candidate
table, and row-review table are intentionally excluded.

## Included Files

- `selection_summary.csv`: selected count by Open-Patients source group.
- `source_manifest.csv`: source, URL, and license metadata for each selected
  row.
- `manual_review.md`: dated manual smoke-review summary from the local run.

## Source Composition

| Source group | Count |
| --- | ---: |
| TREC CDS 2014 | 30 |
| TREC CDS 2015 | 30 |
| TREC CDS 2016 | 30 |
| TREC CT 2021 | 75 |
| TREC CT 2022 | 50 |
| PMC-Patients | 450 |
| USMLE-style cases | 335 |

## Review Method

The smoke test was run using Codex with GPT-5.5. Potential issues identified by
the coding agent were checked manually before source-code changes were
considered. This is a smoke review without gold labels.

## Source And License Notes

The source manifest records NCBI Open-Patients as the dataset source and
CC-BY-SA-4.0 as listed on the Hugging Face dataset card at the time this local
smoke set was created. Users should review the upstream dataset card and
license terms before rebuilding or redistributing note text.
