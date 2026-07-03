# External Smoke-Review Summaries

This folder contains summaries from larger ProjectPHI smoke reviews over
external public clinical-text resources. It is intended to document review
method, source composition, and issue profiles without committing raw note text
or full row-level audit outputs.

## Review Method

The smoke tests were run using Codex with GPT-5.5. Potential issues identified
by the coding agent were checked manually before source-code changes were
considered. These reviews are smoke tests, not gold-standard evaluations.

## Included

- source manifests with source/license/access metadata;
- selection summaries;
- manual review summaries for the 1k run and five 2k chunk runs;
- an aggregate summary of source composition and review status.

## Not Included

This folder intentionally excludes raw input notes, de-identified output notes,
full audit outputs, issue-candidate tables, row-review tables, and chunk input
CSVs. Those local artifacts can contain copied public clinical text or copied
row-level context from public sources. Keeping this folder summary-only avoids
turning the ProjectPHI repository into a redistributor of the underlying note
corpora.

## Source And License Notes

The manifests record dataset/source URLs and license or access notes available
when the local smoke sets were built. Downstream users are responsible for
reviewing and following the original source licenses, terms of use, and access
requirements before rebuilding or redistributing any underlying note text.

## Subfolders

- `open_patients_1000/`: 1000-note Open-Patients smoke-review summary.
- `mixed_external_10000/`: 10000-row mixed external smoke-review summaries,
  reviewed as five 2000-row chunks.
