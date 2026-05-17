"""Stable date-shift behavior and offset-separation tests.

These tests cover ProjectPHI's stable date-shifting policy for pyDeid-detected
date spans.

Main contracts covered:
- the same patient/secret pair gets the same deterministic day offset;
- all parseable dates for one patient use the same offset;
- intervals between dates are preserved after shifting;
- ISO full dates and supported English full dates are shifted safely;
- supported `Month YYYY` spans are shifted with an internal anchor day while
  preserving visible month/year granularity;
- year-only, time, holiday/season, and unparseable date-like spans are handled
  by preservation or safe fallback policy;
- original-note offsets, pyDeid surrogate offsets, and ProjectPHI final
  replacement offsets remain separate;
- secrets, raw note text, and raw unparseable date text are not copied into
  warnings/errors.

All examples are synthetic.
"""

from datetime import date, datetime, timedelta

import pytest

from project_phi import PHISpan, deidentify_note
import project_phi.reconstruction as reconstruction
from conftest import _date_spans


def _natural_date(text):
    return datetime.strptime(text, "%B %d, %Y").date()


def _month_year_date(text):
    return datetime.strptime(text, "%B %Y").date()


def test_stable_date_shift_is_deterministic_for_same_patient_secret_and_note():
    note = "Follow-up on 2001-12-10."

    first = deidentify_note(
        note,
        patient_id="Patient/synth-date-001",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )
    second = deidentify_note(
        note,
        patient_id="Patient/synth-date-001",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    assert first.deidentified_text == second.deidentified_text
    assert _date_spans(first)[0].replacement == _date_spans(second)[0].replacement

def test_stable_date_shift_preserves_interval_between_dates():
    note = "Follow-up on 2001-12-10 and review on 2002-01-09."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-date-002",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    original_dates = [date.fromisoformat(span.text) for span in _date_spans(result)]
    shifted_dates = [date.fromisoformat(span.replacement) for span in _date_spans(result)]
    # Stable per-patient shifting should preserve within-patient intervals.
    assert len(shifted_dates) >= 2
    assert shifted_dates[1] - shifted_dates[0] == original_dates[1] - original_dates[0]

def test_stable_date_shift_shifts_natural_language_full_dates():
    note = "Follow-up on March 14, 2026."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-date-natural-001",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    date_span = _date_spans(result)[0]
    assert "March 14, 2026" not in result.deidentified_text
    assert "<DATE>" not in result.deidentified_text
    assert date_span.replacement != "<DATE>"
    assert _natural_date(date_span.replacement) == _natural_date(date_span.text) + timedelta(
        days=date_span.metadata["project_date_shift_days"]
    )
    assert date_span.metadata["replacement_source"] == "project_stable_date_shift"
    assert date_span.metadata["project_date_shift_policy"] == "shifted_natural_language_full_date"
    assert "project_date_shift_days" in date_span.metadata
    assert date_span.metadata["project_date_shift_range_days"] == 45

    assert note[date_span.start : date_span.end] == date_span.text
    project_start = date_span.metadata["project_replacement_start"]
    project_end = date_span.metadata["project_replacement_end"]
    assert result.deidentified_text[project_start:project_end] == date_span.replacement
    assert "pydeid_surrogate_start" in date_span.metadata
    assert "pydeid_surrogate_end" in date_span.metadata
    assert "March 14, 2026" not in " ".join(result.warnings)

def test_stable_date_shift_preserves_interval_between_natural_language_full_dates():
    note = "Follow-up on February 28, 2026 and review on March 3, 2026."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-date-natural-002",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    spans = _date_spans(result)
    assert len(spans) >= 2
    original_dates = [_natural_date(span.text) for span in spans[:2]]
    shifted_dates = [_natural_date(span.replacement) for span in spans[:2]]
    assert shifted_dates[1] - shifted_dates[0] == original_dates[1] - original_dates[0]
    assert "February 28, 2026" not in result.deidentified_text
    assert "March 3, 2026" not in result.deidentified_text
    assert all(span.replacement != "<DATE>" for span in spans[:2])

def test_stable_date_shift_uses_same_offset_for_iso_and_natural_language_dates():
    note = "Started on 2001-01-05 and follow-up on March 14, 2026."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-date-natural-003",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    iso_span = next(span for span in _date_spans(result) if span.text == "2001-01-05")
    natural_span = next(span for span in _date_spans(result) if span.text == "March 14, 2026")
    assert iso_span.metadata["project_date_shift_days"] == natural_span.metadata["project_date_shift_days"]
    assert date.fromisoformat(iso_span.replacement) == date.fromisoformat(iso_span.text) + timedelta(
        days=natural_span.metadata["project_date_shift_days"]
    )
    assert _natural_date(natural_span.replacement) == _natural_date(natural_span.text) + timedelta(
        days=iso_span.metadata["project_date_shift_days"]
    )
    assert natural_span.metadata["project_date_shift_policy"] == "shifted_natural_language_full_date"

def test_stable_date_shift_shifts_month_year_spans_without_day_granularity():
    note = "Diagnosis in March 2021 and treatment in September 2021."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-month-year-001",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    month_year_spans = [
        span
        for span in _date_spans(result)
        if span.metadata.get("project_date_shift_policy") == "shifted_month_year"
    ]
    assert len(month_year_spans) >= 2
    assert "March 2021" not in result.deidentified_text
    assert "September 2021" not in result.deidentified_text
    assert "<DATE>" not in result.deidentified_text
    assert month_year_spans[0].replacement == "April 2021"
    assert month_year_spans[1].replacement == "October 2021"

    for span in month_year_spans:
        assert span.replacement != "<DATE>"
        assert _month_year_date(span.replacement)
        assert span.metadata["replacement_source"] == "project_stable_date_shift"
        assert span.metadata["project_date_shift_days"] == 42
        assert span.metadata["project_date_shift_range_days"] == 45
        assert span.metadata["project_date_shift_granularity"] == "month_year"
        assert span.metadata["project_date_shift_anchor_day"] == 15
        assert note[span.start : span.end] == span.text
        project_start = span.metadata["project_replacement_start"]
        project_end = span.metadata["project_replacement_end"]
        assert result.deidentified_text[project_start:project_end] == span.replacement
        assert "pydeid_surrogate_start" in span.metadata
        assert "pydeid_surrogate_end" in span.metadata

def test_stable_date_shift_month_year_preserves_timeline_ordering():
    note = (
        "Diagnosis in March 2021. Chemotherapy completed in September 2021. "
        "Endocrine therapy started in October 2021. Surveillance planned in April 2027."
    )

    result = deidentify_note(
        note,
        patient_id="Patient/synth-month-year-001",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    month_year_spans = [
        span
        for span in _date_spans(result)
        if span.metadata.get("project_date_shift_policy") == "shifted_month_year"
    ]
    shifted_months = [_month_year_date(span.replacement) for span in month_year_spans]
    assert len(shifted_months) >= 4
    assert shifted_months == sorted(shifted_months)
    assert all(span.replacement != "<DATE>" for span in month_year_spans)
    assert "Diagnosis in" in result.deidentified_text
    assert "Chemotherapy completed in" in result.deidentified_text
    assert "Endocrine therapy started in" in result.deidentified_text
    assert "Surveillance planned in" in result.deidentified_text

def test_stable_date_shift_month_year_zero_range_preserves_visible_month_and_metadata():
    note = "Diagnosis in March 2021."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-month-year-003",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
        date_shift_days=0,
    )

    span = next(
        span
        for span in _date_spans(result)
        if span.metadata.get("project_date_shift_policy") == "shifted_month_year"
    )
    assert "March 2021" in result.deidentified_text
    assert span.replacement == "March 2021"
    assert span.metadata["project_date_shift_days"] == 0
    assert span.metadata["project_date_shift_range_days"] == 0
    assert span.metadata["project_date_shift_granularity"] == "month_year"
    assert span.metadata["project_date_shift_anchor_day"] == 15

def test_stable_date_shift_month_year_uses_same_patient_offset_as_full_date():
    note = "Diagnosis in March 2021. Follow-up on March 14, 2026."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-month-year-001",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    month_year_span = next(
        span
        for span in _date_spans(result)
        if span.metadata.get("project_date_shift_policy") == "shifted_month_year"
    )
    full_date_span = next(
        span
        for span in _date_spans(result)
        if span.metadata.get("project_date_shift_policy") == "shifted_natural_language_full_date"
    )
    assert month_year_span.metadata["project_date_shift_days"] == full_date_span.metadata["project_date_shift_days"]
    assert _natural_date(full_date_span.replacement) == _natural_date(full_date_span.text) + timedelta(
        days=month_year_span.metadata["project_date_shift_days"]
    )

def test_stable_date_shift_removes_original_date_and_keeps_non_date_phi_replaced():
    note = "Test MRN: 011-0111. Follow-up on 2001-12-10."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-date-003",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    assert "2001-12-10" not in result.deidentified_text
    assert "011-0111" not in result.deidentified_text
    assert any(span.label == "ID" and span.replacement != span.text for span in result.spans)

def test_stable_date_shift_keeps_original_and_project_offsets_separate():
    note = "Test MRN: 011-0111. Follow-up on 2001-12-10."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-date-004",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    date_span = _date_spans(result)[0]
    # Original span offsets still slice the source note; project offsets slice
    # the reconstructed de-identified text.
    assert note[date_span.start : date_span.end] == date_span.text
    project_start = date_span.metadata["project_replacement_start"]
    project_end = date_span.metadata["project_replacement_end"]
    assert result.deidentified_text[project_start:project_end] == date_span.replacement
    assert "pydeid_surrogate_start" in date_span.metadata
    assert "pydeid_surrogate_end" in date_span.metadata
    assert "pydeid_replacement" in date_span.metadata

def test_stable_date_shift_requires_patient_id_and_secret():
    note = "Follow-up on 2001-12-10."

    with pytest.raises(ValueError, match="patient_id"):
        deidentify_note(
            note,
            stable_date_shift=True,
            date_shift_secret="synthetic-secret",
        )
    with pytest.raises(ValueError, match="date_shift_secret"):
        deidentify_note(
            note,
            patient_id="Patient/synth-date-005",
            stable_date_shift=True,
        )

def test_stable_date_shift_zero_range_keeps_full_date_and_records_metadata():
    note = "Follow-up on 2001-12-10."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-date-006",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
        date_shift_days=0,
    )

    date_span = _date_spans(result)[0]
    assert "2001-12-10" in result.deidentified_text
    assert date_span.replacement == "2001-12-10"
    assert date_span.metadata["replacement_source"] == "project_stable_date_shift"
    assert date_span.metadata["project_date_shift_days"] == 0
    assert date_span.metadata["project_date_shift_range_days"] == 0
    assert date_span.metadata["project_date_shift_policy"] == "shifted_full_date"

def test_stable_date_shift_secret_env_var_success(monkeypatch):
    note = "Follow-up on 2001-12-10."
    monkeypatch.setenv("PROJECT_PHI_TEST_DATE_SECRET", "synthetic-secret")

    result = deidentify_note(
        note,
        patient_id="Patient/synth-date-007",
        stable_date_shift=True,
        date_shift_secret_env_var="PROJECT_PHI_TEST_DATE_SECRET",
    )

    assert _date_spans(result)
    assert "2001-12-10" not in result.deidentified_text

def test_stable_date_shift_secret_env_var_missing_or_empty_raises(monkeypatch):
    note = "Follow-up on 2001-12-10."
    monkeypatch.delenv("PROJECT_PHI_MISSING_DATE_SECRET", raising=False)

    with pytest.raises(ValueError, match="date_shift_secret"):
        deidentify_note(
            note,
            patient_id="Patient/synth-date-008",
            stable_date_shift=True,
            date_shift_secret_env_var="PROJECT_PHI_MISSING_DATE_SECRET",
        )

    monkeypatch.setenv("PROJECT_PHI_EMPTY_DATE_SECRET", "")
    with pytest.raises(ValueError, match="date_shift_secret"):
        deidentify_note(
            note,
            patient_id="Patient/synth-date-008",
            stable_date_shift=True,
            date_shift_secret_env_var="PROJECT_PHI_EMPTY_DATE_SECRET",
        )

def test_stable_date_shift_invalid_shift_days_raise():
    note = "Follow-up on 2001-12-10."

    with pytest.raises(ValueError, match="date_shift_days"):
        deidentify_note(
            note,
            patient_id="Patient/synth-date-009",
            stable_date_shift=True,
            date_shift_secret="synthetic-secret",
            date_shift_days=-1,
        )
    with pytest.raises(ValueError, match="date_shift_days"):
        deidentify_note(
            note,
            patient_id="Patient/synth-date-009",
            stable_date_shift=True,
            date_shift_secret="synthetic-secret",
            date_shift_days="45",
        )

def test_stable_date_shift_requires_date_detection_when_types_are_provided():
    note = "Test MRN: 011-0111. Follow-up on 2001-12-10."

    with pytest.raises(ValueError, match="date detection"):
        deidentify_note(
            note,
            patient_id="Patient/synth-date-010",
            stable_date_shift=True,
            date_shift_secret="synthetic-secret",
            types=["mrn"],
        )

def test_stable_date_shift_overlap_failure_is_sanitized():
    note = "Synthetic overlap 2001-12-10."
    raw_span_text = "2001-12-10"
    spans = [
        PHISpan(
            start=18,
            end=28,
            text=raw_span_text,
            label="DATE",
            source="pyDeid",
            replacement="2001-12-11",
            pydeid_types=["Date"],
            metadata={},
        ),
        PHISpan(
            start=20,
            end=28,
            text="01-12-10",
            label="DATE",
            source="pyDeid",
            replacement="2001-12-11",
            pydeid_types=["Date"],
            metadata={},
        ),
    ]

    with pytest.raises(ValueError) as exc_info:
        reconstruction._reconstruct_with_stable_dates(
            note,
            spans,
            date_shift_offset=1,
            date_shift_days=45,
        )

    message = str(exc_info.value)
    assert "Overlapping pyDeid spans" in message
    assert raw_span_text not in message
    assert note not in message

def test_stable_date_shift_unparseable_date_placeholder_warning_is_sanitized():
    note = "Approximate date Spring."
    spans = [
        PHISpan(
            start=17,
            end=23,
            text="Spring",
            label="DATE",
            source="pyDeid",
            replacement="May",
            pydeid_types=["Date"],
            metadata={},
        )
    ]

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        spans,
        date_shift_offset=1,
        date_shift_days=45,
    )

    warning_text = " ".join(warnings)
    assert deidentified_text == "Approximate date <DATE>."
    assert final_spans[0].replacement == "<DATE>"
    assert "Unparseable pyDeid date span" in warning_text
    assert "Spring" not in warning_text
    assert note not in warning_text

def test_stable_date_shift_unsupported_partial_natural_date_fallback_is_sanitized():
    note = "Approximate partial date March 14."
    spans = [
        PHISpan(
            start=25,
            end=33,
            text="March 14",
            label="DATE",
            source="pyDeid",
            replacement="May 14",
            pydeid_types=["Date"],
            metadata={},
        )
    ]

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        spans,
        date_shift_offset=1,
        date_shift_days=45,
    )

    warning_text = " ".join(warnings)
    assert deidentified_text == "Approximate partial date <DATE>."
    assert final_spans[0].replacement == "<DATE>"
    assert "Unparseable pyDeid date span" in warning_text
    assert "March 14" not in warning_text
    assert note not in warning_text
