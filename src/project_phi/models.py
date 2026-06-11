"""Shared result models for ProjectPHI de-identification.

These immutable dataclasses define the result shape used by the pipeline.
They do not perform detection, pruning, replacement, or audit generation.

Offset convention:
- `PHISpan.start` and `PHISpan.end` refer to the original input note.
- pyDeid surrogate offsets may be stored in `PHISpan.metadata` as
  `pydeid_surrogate_start` / `pydeid_surrogate_end`.
- Final replacement offsets may be stored in `PHISpan.metadata` as
  `project_replacement_start` / `project_replacement_end`.

Keeping these coordinate systems separate avoids ambiguity when replacements
change the length of the note text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PHISpan:
    """One detected PHI span in ProjectPHI's normalized result format.

    The dataclass is frozen so downstream steps create updated copies instead of
    mutating spans in place. This keeps audit/debug state explicit.

    Attributes:
        start: Start character offset in the original input note.
        end: End character offset in the original input note. For a well-formed
            span, `original_text[start:end]` should equal `text`.
        text: Original detected text. Useful for in-memory inspection and tests;
            persistent audit outputs should not include raw detected PHI by default.
        label: Project-normalized PHI category, such as `DATE`, `NAME`,
            `CONTACT`, `LOCATION`, `HOSPITAL`, `ID`, `TIME`, or `PHI`.
        source: Detection provenance, usually `pyDeid`.
        confidence: Optional detector confidence score. pyDeid detections
            usually leave this as `None`.
        rule_id: Optional project rule identifier.
        section: Optional note-section context for future segmentation or audit work.
        action: Final handling decision, such as `replaced` or `preserved`.
        replacement: Final replacement text used for this span.
        pydeid_types: Raw pyDeid type strings kept for provenance.
        metadata: Extension dictionary for IDs, offsets, policy details, and
            detector-specific provenance.
    """

    start: int
    end: int
    text: str
    label: str
    source: str
    confidence: float | None = None
    rule_id: str | None = None
    section: str | None = None
    action: str | None = None
    replacement: str | None = None
    pydeid_types: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeidentificationResult:
    """Structured result for one de-identified note.

    Attributes:
        original_text: Original input note when retained in memory. Avoid copying
            this into persistent audit outputs by default.
        deidentified_text: Final de-identified note text.
        spans: Normalized spans with final replacement/action metadata.
        warnings: Sanitized note-level warnings. Avoid raw note text, raw PHI,
            aliases, regex patterns, secrets, hashes, or HMAC digests.
        metadata: Note-level IDs, options, summary values, and provenance details.
    """

    original_text: str | None
    deidentified_text: str
    spans: list[PHISpan]
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PatientDeidentificationResult:
    """Structured result for one patient's batch de-identification run.

    The batch API is intended for per-patient timelines where all notes for one
    patient should share date-shift and optional unknown-name surrogate policy.
    `results` preserves the input note order.
    """

    patient_id: str
    results: list[DeidentificationResult]
    date_shift_offset_days: int | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
