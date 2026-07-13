"""Stable date-shift behavior and offset-separation tests."""

from datetime import date, datetime, timedelta

import pytest

from project_phi import PHISpan, deidentify_note, get_patient_date_shift
import project_phi.reconstruction as reconstruction
from conftest import _date_spans


def _natural_date(text):
    return datetime.strptime(text, "%B %d, %Y").date()


def _day_month_year_date(text):
    return datetime.strptime(text, "%d %B %Y").date()


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


def test_get_patient_date_shift_matches_note_level_date_shift_metadata():
    note = "Follow-up on 2001-12-10."
    patient_id = "Patient/synth-date-public-001"

    offset = get_patient_date_shift(
        patient_id=patient_id,
        date_shift_secret="synthetic-secret",
    )
    result = deidentify_note(
        note,
        patient_id=patient_id,
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    date_span = _date_spans(result)[0]
    assert offset == date_span.metadata["project_date_shift_days"]
    assert date.fromisoformat(date_span.replacement) == (
        date.fromisoformat(date_span.text) + timedelta(days=offset)
    )


def test_get_patient_date_shift_is_deterministic_and_bounded():
    first = get_patient_date_shift(
        patient_id="Patient/synth-date-public-002",
        date_shift_secret="synthetic-secret",
        date_shift_days=45,
    )
    second = get_patient_date_shift(
        patient_id="Patient/synth-date-public-002",
        date_shift_secret="synthetic-secret",
        date_shift_days=45,
    )

    assert first == second
    assert -45 <= first <= 45


def test_get_patient_date_shift_uses_environment_secret(monkeypatch):
    monkeypatch.setenv("PROJECT_PHI_TEST_DATE_SECRET", "synthetic-secret")

    direct = get_patient_date_shift(
        patient_id="Patient/synth-date-public-003",
        date_shift_secret="synthetic-secret",
    )
    from_env = get_patient_date_shift(
        patient_id="Patient/synth-date-public-003",
        date_shift_secret_env_var="PROJECT_PHI_TEST_DATE_SECRET",
    )

    assert from_env == direct


def test_get_patient_date_shift_zero_range_returns_zero():
    assert (
        get_patient_date_shift(
            patient_id="Patient/synth-date-public-004",
            date_shift_secret="synthetic-secret",
            date_shift_days=0,
        )
        == 0
    )


def test_get_patient_date_shift_validates_inputs(monkeypatch):
    monkeypatch.delenv("PROJECT_PHI_TEST_DATE_SECRET", raising=False)

    with pytest.raises(ValueError, match="patient_id"):
        get_patient_date_shift(
            patient_id="",
            date_shift_secret="synthetic-secret",
        )
    with pytest.raises(ValueError, match="date_shift_secret"):
        get_patient_date_shift(patient_id="Patient/synth-date-public-005")
    with pytest.raises(ValueError, match="date_shift_secret"):
        get_patient_date_shift(
            patient_id="Patient/synth-date-public-005",
            date_shift_secret_env_var="PROJECT_PHI_TEST_DATE_SECRET",
        )
    with pytest.raises(ValueError, match="date_shift_days"):
        get_patient_date_shift(
            patient_id="Patient/synth-date-public-005",
            date_shift_secret="synthetic-secret",
            date_shift_days=-1,
        )


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

def test_stable_date_shift_shifts_day_month_year_natural_language_dates():
    note = "Follow-up occurred on 8 August 2019."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-date-day-month-001",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    date_span = _date_spans(result)[0]
    assert "8 August 2019" not in result.deidentified_text
    assert "<DATE>" not in result.deidentified_text
    assert date_span.replacement != "<DATE>"
    assert _day_month_year_date(date_span.replacement) == _day_month_year_date(
        date_span.text
    ) + timedelta(days=date_span.metadata["project_date_shift_days"])
    assert date_span.metadata["replacement_source"] == "project_stable_date_shift"
    assert date_span.metadata["project_date_shift_policy"] == (
        "shifted_day_month_year_natural_language_full_date"
    )
    assert note[date_span.start : date_span.end] == date_span.text
    project_start = date_span.metadata["project_replacement_start"]
    project_end = date_span.metadata["project_replacement_end"]
    assert result.deidentified_text[project_start:project_end] == date_span.replacement
    assert "8 August 2019" not in " ".join(result.warnings)

def test_stable_date_shift_day_month_year_preserves_interval_between_dates():
    note = "Started on 8 August 2019 and stopped on 25 August 2019."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-date-day-month-002",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    spans = _date_spans(result)
    assert len(spans) >= 2
    shifted_dates = [_day_month_year_date(span.replacement) for span in spans[:2]]
    original_dates = [_day_month_year_date(span.text) for span in spans[:2]]
    assert shifted_dates[1] - shifted_dates[0] == original_dates[1] - original_dates[0]
    assert all(span.replacement != "<DATE>" for span in spans[:2])

def test_stable_date_shift_uses_same_offset_for_month_day_and_day_month_dates():
    note = "Started on March 14, 2026 and reviewed on 10 April 2026."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-date-day-month-003",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    month_day_span = next(span for span in _date_spans(result) if span.text == "March 14, 2026")
    day_month_span = next(span for span in _date_spans(result) if span.text == "10 April 2026")
    assert month_day_span.metadata["project_date_shift_days"] == day_month_span.metadata[
        "project_date_shift_days"
    ]
    assert _natural_date(month_day_span.replacement) == _natural_date(
        month_day_span.text
    ) + timedelta(days=day_month_span.metadata["project_date_shift_days"])
    assert _day_month_year_date(day_month_span.replacement) == _day_month_year_date(
        day_month_span.text
    ) + timedelta(days=month_day_span.metadata["project_date_shift_days"])

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

def test_stable_date_shift_shifts_partial_month_day_by_default():
    note = "Follow-up on July 15."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-partial-month-day-001",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    span = _date_spans(result)[0]
    assert "<DATE>" not in result.deidentified_text
    assert span.metadata["project_date_shift_policy"] == "shifted_partial_month_day"

def test_stable_date_shift_partial_month_day_can_be_disabled():
    note = "Follow-up on July 15."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-partial-month-day-001",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
        shift_partial_month_day_dates=False,
    )

    assert result.deidentified_text == "Follow-up on <DATE>."
    assert _date_spans(result)[0].metadata["project_date_shift_policy"] == (
        "unparseable_date_placeholder"
    )

def test_stable_date_shift_shifts_partial_month_day_when_explicitly_enabled():
    note = "Follow-up on July 15."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-partial-month-day-001",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
        shift_partial_month_day_dates=True,
    )

    span = _date_spans(result)[0]
    expected = date(2000, 7, 15) + timedelta(days=span.metadata["project_date_shift_days"])
    assert result.deidentified_text == f"Follow-up on {expected.strftime('%B')} {expected.day}."
    assert span.replacement == f"{expected.strftime('%B')} {expected.day}"
    assert span.metadata["replacement_source"] == "project_stable_date_shift"
    assert span.metadata["project_date_shift_policy"] == "shifted_partial_month_day"
    assert span.metadata["project_date_shift_granularity"] == "month_day"
    assert span.metadata["project_date_shift_anchor_year"] == 2000
    assert "project_date_shift_anchor_day" not in span.metadata

def test_stable_date_shift_partial_month_day_handles_abbreviations_and_ordinals():
    note = "Follow-up on Jul 15 and review on July 15th."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-partial-month-day-001",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
        shift_partial_month_day_dates=True,
    )

    spans = _date_spans(result)
    assert len(spans) >= 2
    assert all(span.metadata["project_date_shift_policy"] == "shifted_partial_month_day" for span in spans[:2])
    assert "<DATE>" not in result.deidentified_text
    assert "Jul 15" not in result.deidentified_text
    assert "July 15th" not in result.deidentified_text

def test_stable_date_shift_partial_month_day_boundary_uses_leap_anchor_year():
    note = "Approximate dates January 2 and February 29."
    spans = [
        PHISpan(
            start=18,
            end=27,
            text="January 2",
            label="DATE",
            source="pyDeid",
            replacement="May 1",
            pydeid_types=["Month Day [Month dd]"],
            metadata={"parsed_phi": {"kind": "date", "day": "2", "month": "January", "year": None}},
        ),
        PHISpan(
            start=32,
            end=43,
            text="February 29",
            label="DATE",
            source="pyDeid",
            replacement="May 2",
            pydeid_types=["Month Day [Month dd]"],
            metadata={"parsed_phi": {"kind": "date", "day": "29", "month": "February", "year": None}},
        ),
    ]

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
        date_shift_offset=-5,
        date_shift_days=45,
        shift_partial_month_day_dates=True,
    )

    assert warnings == []
    assert deidentified_text == "Approximate dates December 28 and February 24."
    assert final_spans[0].replacement == "December 28"
    assert final_spans[1].replacement == "February 24"
    assert all(
        span.metadata["project_date_shift_anchor_year"] == 2000
        for span in final_spans
    )

def test_stable_date_shift_preserves_score_fraction_in_date_span():
    note = "The patient scored 1/50 points on the synthetic assessment tool."
    span = PHISpan(
        start=19,
        end=23,
        text="1/50",
        label="DATE",
        source="pyDeid",
        replacement="January 2050",
        pydeid_types=["Month/Year (2) [mm/yy]"],
        metadata={"parsed_phi": {"kind": "date", "month": "1", "year": "50"}},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        [span],
        date_shift_offset=30,
        date_shift_days=45,
    )

    assert deidentified_text == note
    assert warnings == []
    final_span = final_spans[0]
    assert final_span.action == "preserved"
    assert final_span.replacement == "1/50"
    assert final_span.metadata["replacement_source"] == "preserved"
    assert final_span.metadata["project_date_shift_policy"] == "preserved_score_or_fraction"
    assert final_span.metadata["project_date_shift_preservation_reason"] == "score_or_fraction_context"
    project_start = final_span.metadata["project_replacement_start"]
    project_end = final_span.metadata["project_replacement_end"]
    assert deidentified_text[project_start:project_end] == "1/50"

def test_stable_date_shift_preserves_staging_fraction_in_date_span():
    note = "The pathological stage was ypT4 N1 (1/61) M0 after surgery."
    start = note.index("1/61")
    span = PHISpan(
        start=start,
        end=start + len("1/61"),
        text="1/61",
        label="DATE",
        source="pyDeid",
        replacement="February 2061",
        pydeid_types=["Month/Year (2) [mm/yy]"],
        metadata={"parsed_phi": {"kind": "date", "month": "1", "year": "61"}},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        [span],
        date_shift_offset=30,
        date_shift_days=45,
    )

    assert deidentified_text == note
    assert warnings == []
    assert final_spans[0].metadata["project_date_shift_policy"] == "preserved_score_or_fraction"

def test_stable_date_shift_preserves_visual_acuity_fraction_in_date_span():
    note = "Visual acuity in the left eye is 6/60 and right eye is counting fingers."
    start = note.index("6/60")
    span = PHISpan(
        start=start,
        end=start + len("6/60"),
        text="6/60",
        label="DATE",
        source="pyDeid",
        replacement="June 2060",
        pydeid_types=["Month/Year (2) [mm/yy]"],
        metadata={"parsed_phi": {"kind": "date", "month": "6", "year": "60"}},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        [span],
        date_shift_offset=-20,
        date_shift_days=45,
    )

    assert deidentified_text == note
    assert warnings == []
    assert final_spans[0].metadata["project_date_shift_policy"] == "preserved_score_or_fraction"

def test_stable_date_shift_preserves_tumor_marker_numeric_span():
    note = "Tumor markers CA 15-3 and CA 27.29 were elevated."
    start = note.index("15-3")
    span = PHISpan(
        start=start,
        end=start + len("15-3"),
        text="15-3",
        label="DATE",
        source="pyDeid",
        replacement="<DATE>",
        pydeid_types=["Month/Day [mm-dd]"],
        metadata={"parsed_phi": {"kind": "date", "month": "15", "day": "3"}},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        [span],
        date_shift_offset=30,
        date_shift_days=45,
    )

    assert deidentified_text == note
    assert warnings == []
    assert final_spans[0].action == "preserved"
    assert final_spans[0].metadata["project_date_shift_policy"] == "preserved_score_or_fraction"
    assert (
        final_spans[0].metadata["project_date_shift_preservation_reason"]
        == "score_or_fraction_context"
    )

def test_stable_date_shift_shifts_pydeid_numeric_month_day_span():
    note = "Vancomycin was started on 8-29 after cultures."
    start = note.index("8-29")
    span = PHISpan(
        start=start,
        end=start + len("8-29"),
        text="8-29",
        label="DATE",
        source="pyDeid",
        replacement="<DATE>",
        pydeid_types=["Month/Day [mm-dd]"],
        metadata={"parsed_phi": {"kind": "date", "month": "8", "day": "29"}},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        [span],
        date_shift_offset=30,
        date_shift_days=45,
    )

    assert deidentified_text == "Vancomycin was started on September 28 after cultures."
    assert final_spans[0].replacement == "September 28"
    assert final_spans[0].metadata["project_date_shift_policy"] == "shifted_partial_month_day"
    assert final_spans[0].metadata["project_date_shift_granularity"] == "month_day"
    assert final_spans[0].metadata["project_date_shift_anchor_year"] == 2000
    assert warnings == []

def test_stable_date_shift_shifts_placeholder_wrapped_numeric_month_day_span():
    note = "Repair was completed on [**6-17**] without complications."
    start = note.index("[**6-17**]")
    span = PHISpan(
        start=start,
        end=start + len("[**6-17**]"),
        text="[**6-17**]",
        label="DATE",
        source="pyDeid",
        replacement="<DATE>",
        pydeid_types=["Month/Day (3) [mm/dd]"],
        metadata={"parsed_phi": {"kind": "date", "month": "6", "day": "17"}},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        [span],
        date_shift_offset=9,
        date_shift_days=45,
    )

    assert deidentified_text == "Repair was completed on June 26 without complications."
    assert warnings == []
    assert final_spans[0].metadata["project_date_shift_policy"] == "shifted_partial_month_day"

def test_stable_date_shift_does_not_parse_numeric_month_day_without_pydeid_month_day_type():
    note = "The clinical code was 6-17."
    start = note.index("6-17")
    span = PHISpan(
        start=start,
        end=start + len("6-17"),
        text="6-17",
        label="DATE",
        source="pyDeid",
        replacement="<DATE>",
        pydeid_types=["Other Date"],
        metadata={},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        [span],
        date_shift_offset=9,
        date_shift_days=45,
    )

    assert deidentified_text == "The clinical code was <DATE>."
    assert final_spans[0].metadata["project_date_shift_policy"] == "unparseable_date_placeholder"
    assert warnings == ["Unparseable pyDeid date span replaced with <DATE>."]

def test_stable_date_shift_does_not_parse_numeric_month_day_non_date_span():
    note = "The clinical code was 6-17."
    start = note.index("6-17")
    span = PHISpan(
        start=start,
        end=start + len("6-17"),
        text="6-17",
        label="NAME",
        source="pyDeid",
        replacement="Carter",
        pydeid_types=["Month/Day (3) [mm/dd]"],
        metadata={"parsed_phi": {"kind": "date", "month": "6", "day": "17"}},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        [span],
        date_shift_offset=9,
        date_shift_days=45,
    )

    assert deidentified_text == "The clinical code was <DATE>."
    assert final_spans[0].metadata["project_date_shift_policy"] == "unparseable_date_placeholder"
    assert warnings == ["Unparseable pyDeid date span replaced with <DATE>."]

def test_stable_date_shift_preserves_apgar_slash_score_in_date_span():
    note = "Apgar scores were 4/7/10 at 1, 5 and 10 min after delivery."
    start = note.index("4/7/10")
    span = PHISpan(
        start=start,
        end=start + len("4/7/10"),
        text="4/7/10",
        label="DATE",
        source="pyDeid",
        replacement="0010-04-07",
        pydeid_types=["Year/Month/Day [yy(yy)/mm/dd]"],
        metadata={"parsed_phi": {"kind": "date", "month": "4", "day": "7", "year": "10"}},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        [span],
        date_shift_offset=30,
        date_shift_days=45,
    )

    assert deidentified_text == note
    assert warnings == []
    assert final_spans[0].action == "preserved"
    assert final_spans[0].metadata["project_date_shift_policy"] == "preserved_score_or_fraction"
    assert (
        final_spans[0].metadata["project_date_shift_preservation_reason"]
        == "score_or_fraction_context"
    )

def test_stable_date_shift_still_shifts_three_part_slash_date_without_apgar_context():
    note = "Follow-up occurred on 4/7/2010."
    start = note.index("4/7/2010")
    span = PHISpan(
        start=start,
        end=start + len("4/7/2010"),
        text="4/7/2010",
        label="DATE",
        source="pyDeid",
        replacement="2010-04-07",
        pydeid_types=["Month/Day/Year [mm/dd/yy(yy)]"],
        metadata={"parsed_phi": {"kind": "date", "month": "4", "day": "7", "year": "2010"}},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        [span],
        date_shift_offset=30,
        date_shift_days=45,
    )

    assert "4/7/2010" not in deidentified_text
    assert final_spans[0].replacement == "2010-05-07"
    assert final_spans[0].metadata["project_date_shift_policy"] == "shifted_full_date"
    assert warnings == []

def test_stable_date_shift_still_shifts_three_part_slash_date_near_apgar_without_timing_context():
    note = "Apgar scores were recorded. Follow-up occurred on 4/7/2010."
    start = note.index("4/7/2010")
    span = PHISpan(
        start=start,
        end=start + len("4/7/2010"),
        text="4/7/2010",
        label="DATE",
        source="pyDeid",
        replacement="2010-04-07",
        pydeid_types=["Month/Day/Year [mm/dd/yy(yy)]"],
        metadata={"parsed_phi": {"kind": "date", "month": "4", "day": "7", "year": "2010"}},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        [span],
        date_shift_offset=-7,
        date_shift_days=45,
    )

    assert "4/7/2010" not in deidentified_text
    assert final_spans[0].replacement == "2010-03-31"
    assert final_spans[0].metadata["project_date_shift_policy"] == "shifted_full_date"
    assert warnings == []

def test_stable_date_shift_still_shifts_slash_month_year_without_fraction_context():
    note = "Follow-up occurred in 10/2021."
    start = note.index("10/2021")
    span = PHISpan(
        start=start,
        end=start + len("10/2021"),
        text="10/2021",
        label="DATE",
        source="pyDeid",
        replacement="January 2022",
        pydeid_types=["Month/Year 1 [mm/yy(yy)]"],
        metadata={"parsed_phi": {"kind": "date", "month": "10", "year": "2021"}},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        [span],
        date_shift_offset=31,
        date_shift_days=45,
    )

    assert "10/2021" not in deidentified_text
    assert final_spans[0].replacement == "November 2021"
    assert final_spans[0].metadata["project_date_shift_policy"] == "shifted_month_year"
    assert warnings == []

def test_reconstruction_preserves_pmhx_site_acronym_overlap():
    note = "A 75F with a PMHx significant for severe PVD."
    start = note.index("PMH")
    span = PHISpan(
        start=start,
        end=start + len("PMH"),
        text="PMH",
        label="HOSPITAL",
        source="pyDeid",
        replacement="SMH",
        pydeid_types=["Site Acronym"],
        metadata={
            "pydeid_replacement": "SMH",
            "pydeid_surrogate_start": start,
            "pydeid_surrogate_end": start + len("SMH"),
        },
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
    )

    assert deidentified_text == note
    assert warnings == []
    final_span = final_spans[0]
    assert final_span.action == "preserved"
    assert final_span.replacement == "PMH"
    assert final_span.metadata["replacement_source"] == "project_clinical_abbreviation_veto"
    assert (
        final_span.metadata["project_clinical_abbreviation_policy"]
        == "preserved_pmhx_site_acronym_overlap"
    )
    assert final_span.metadata["project_clinical_abbreviation"] == "PMHx"

def test_reconstruction_preserves_standalone_pmh_case_insensitive():
    examples = [
        ("PMH - breast cancer, degenerative spinal stenosis", "PMH"),
        ("pmh: breast cancer, degenerative spinal stenosis", "pmh"),
        ("Pmh includes breast cancer.", "Pmh"),
        ("Transferred from PMH for review.", "PMH"),
    ]

    for note, token in examples:
        start = note.index(token)
        span = PHISpan(
            start=start,
            end=start + len(token),
            text=token,
            label="HOSPITAL",
            source="pyDeid",
            replacement="SMH",
            pydeid_types=["Site Acronym"],
            metadata={},
        )

        deidentified_text, final_spans, warnings = (
            reconstruction._reconstruct_with_project_replacements(note, [span])
        )

        assert deidentified_text == note
        assert warnings == []
        assert final_spans[0].action == "preserved"
        assert (
            final_spans[0].metadata["replacement_source"]
            == "project_clinical_abbreviation_veto"
        )
        assert (
            final_spans[0].metadata["project_clinical_abbreviation_policy"]
            == "preserved_standalone_pmh"
        )
        assert final_spans[0].metadata["project_clinical_abbreviation"] == token
        assert (
            final_spans[0].metadata["project_clinical_abbreviation_context"]
            == "past_medical_history"
        )


def test_reconstruction_does_not_preserve_pmh_inside_larger_tokens():
    examples = [
        ("PMHC was listed as the source.", "PMH"),
        ("XPMH was listed as the source.", "PMH"),
        ("pmhClinic was listed as the source.", "pmh"),
    ]

    for note, token in examples:
        start = note.index(token)
        span = PHISpan(
            start=start,
            end=start + len(token),
            text=token,
            label="HOSPITAL",
            source="pyDeid",
            replacement="SMH",
            pydeid_types=["Site Acronym"],
            metadata={},
        )

        deidentified_text, final_spans, warnings = (
            reconstruction._reconstruct_with_project_replacements(note, [span])
        )

        assert "SMH" in deidentified_text
        assert warnings == []
        assert final_spans[0].metadata["replacement_source"] == "pyDeid"

def test_reconstruction_preserves_standalone_pmh_in_medical_history_context():
    note = "This patient has PMH of PCOS, obesity, and HTN."
    start = note.index("PMH")
    span = PHISpan(
        start=start,
        end=start + len("PMH"),
        text="PMH",
        label="HOSPITAL",
        source="pyDeid",
        replacement="SMH",
        pydeid_types=["Site Acronym"],
        metadata={},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
    )

    assert deidentified_text == note
    assert warnings == []
    assert final_spans[0].action == "preserved"
    assert final_spans[0].metadata["replacement_source"] == "project_clinical_abbreviation_veto"
    assert (
        final_spans[0].metadata["project_clinical_abbreviation_policy"]
        == "preserved_clinical_abbreviation_context"
    )
    assert final_spans[0].metadata["project_clinical_abbreviation_context"] == "past_medical_history"

def test_reconstruction_preserves_context_bound_clinical_abbreviations():
    examples = [
        ("The CT head showed SAH from aneurysm rupture.", "SAH", "subarachnoid_hemorrhage"),
        ("IHC showed intact expression of MSH2 and MSH6.", "MSH", "mismatch_repair"),
        ("Whole exome sequencing WES identified a variant.", "WES", "whole_exome_sequencing"),
        ("The echo showed SAM from subaortic membrane.", "SAM", "subaortic_membrane"),
        ("AMAN variant of Guillain-Barre syndrome was considered.", "AMAN", "acute_motor_axonal_neuropathy"),
        ("The NIA-AA criteria were applied.", "NIA", "nia_aa_criteria"),
        ("Traumatic SAH was treated with nimodipine.", "SAH", "subarachnoid_hemorrhage"),
        ("Subaortic membrane caused obstruction and SAM persisted.", "SAM", "subaortic_membrane"),
    ]

    for note, token, context_name in examples:
        start = note.index(token)
        span = PHISpan(
            start=start,
            end=start + len(token),
            text=token,
            label="HOSPITAL",
            source="pyDeid",
            replacement="SMH",
            pydeid_types=["Site Acronym"],
            metadata={},
        )

        deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
            note,
            [span],
        )

        assert deidentified_text == note
        assert warnings == []
        assert final_spans[0].metadata["replacement_source"] == "project_clinical_abbreviation_veto"
        assert final_spans[0].metadata["project_clinical_abbreviation_context"] == context_name

def test_reconstruction_does_not_preserve_context_bound_abbreviation_without_context():
    note = "Transferred from SAH for review."
    start = note.index("SAH")
    span = PHISpan(
        start=start,
        end=start + len("SAH"),
        text="SAH",
        label="HOSPITAL",
        source="pyDeid",
        replacement="SMH",
        pydeid_types=["Site Acronym"],
        metadata={},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
    )

    assert deidentified_text == "Transferred from SMH for review."
    assert warnings == []
    assert final_spans[0].metadata["replacement_source"] == "pyDeid"

def test_reconstruction_preserves_strict_obstetric_history_shorthand():
    note = "A 28 year old female G1P0A0 was admitted."
    start = note.index("G1P0A0")
    span = PHISpan(
        start=start,
        end=start + len("G1P0A0"),
        text="G1P0A0",
        label="LOCATION",
        source="pyDeid",
        replacement="E6V0W8",
        pydeid_types=["Postal Code"],
        metadata={},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
    )

    assert deidentified_text == note
    assert warnings == []
    assert final_spans[0].action == "preserved"
    assert final_spans[0].metadata["replacement_source"] == "project_obstetric_history_veto"
    assert (
        final_spans[0].metadata["project_obstetric_history_policy"]
        == "preserved_strict_obstetric_shorthand"
    )

def test_reconstruction_obstetric_history_veto_does_not_preserve_random_codes():
    note = "The study code G1-PATIENT was listed."
    start = note.index("G1-PATIENT")
    span = PHISpan(
        start=start,
        end=start + len("G1-PATIENT"),
        text="G1-PATIENT",
        label="ID",
        source="pyDeid",
        replacement="SYN-1234",
        pydeid_types=["ID"],
        metadata={},
    )

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
    )

    assert deidentified_text == "The study code SYN-1234 was listed."
    assert warnings == []
    assert final_spans[0].metadata["replacement_source"] == "pyDeid"

def test_deidentify_note_preserves_pmhx_when_pydeid_flags_pmh_substring():
    note = "A 75F with a PMHx significant for severe PVD."

    result = deidentify_note(note, patient_id="Patient/synth-pmhx-001")

    assert "PMHx" in result.deidentified_text
    pmh_span = next(span for span in result.spans if span.text == "PMH")
    assert pmh_span.metadata["replacement_source"] == "project_clinical_abbreviation_veto"

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


def test_stable_date_shift_metadata_is_limited_to_date_like_spans():
    note = "Test MRN: 011-0111. Follow-up on 2001-12-10."

    result = deidentify_note(
        note,
        patient_id="Patient/synth-date-006b",
        stable_date_shift=True,
        date_shift_secret="synthetic-secret",
    )

    date_span = next(span for span in result.spans if span.label == "DATE")
    non_date_spans = [span for span in result.spans if span.label != "DATE"]

    assert date_span.metadata["project_date_shift_policy"] == "shifted_full_date"
    assert date_span.metadata["project_date_shift_range_days"] == 45
    assert non_date_spans
    for span in non_date_spans:
        assert "project_date_shift_policy" not in span.metadata
        assert "project_date_shift_range_days" not in span.metadata
        assert "project_date_shift_days" not in span.metadata


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

def test_stable_date_shift_prunes_recoverable_overlap_with_sanitized_warning():
    note = "Synthetic overlap March 14, 2026."
    raw_span_text = "March 14, 2026"
    start = note.index(raw_span_text)
    spans = [
        PHISpan(
            start=start,
            end=start + len(raw_span_text),
            text=raw_span_text,
            label="DATE",
            source="pyDeid",
            replacement="March 15, 2026",
            pydeid_types=["Date"],
            metadata={},
        ),
        PHISpan(
            start=start + 2,
            end=start + len(raw_span_text),
            text="rch 14, 2026",
            label="DATE",
            source="pyDeid",
            replacement="March 15, 2026",
            pydeid_types=["Date"],
            metadata={},
        ),
    ]

    text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        spans,
        date_shift_offset=1,
        date_shift_days=45,
    )

    warning_text = " ".join(warnings)
    assert text == "Synthetic overlap March 15, 2026."
    assert len(final_spans) == 1
    assert final_spans[0].text == raw_span_text
    assert "Overlapping pyDeid span dropped during reconstruction." in warnings
    assert raw_span_text not in warning_text
    assert note not in warning_text


def test_stable_date_shift_unresolved_overlap_still_fails_safely():
    note = "Synthetic mixed overlap 2001-12-10."
    spans = [
        PHISpan(
            start=24,
            end=34,
            text="2001-12-10",
            label="DATE",
            source="pyDeid",
            replacement="2001-12-11",
            pydeid_types=["Date"],
            metadata={},
        ),
        PHISpan(
            start=26,
            end=36,
            text="01-12-10.",
            label="NAME",
            source="pyDeid",
            replacement="Carter",
            pydeid_types=["Last Name (un)"],
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
    assert note not in message


def test_stable_date_shift_shifts_day_month_year_dates_with_optional_comma():
    note = "The patient was admitted on 15 August, 2003."
    raw_date = "15 August, 2003"
    spans = [
        PHISpan(
            start=note.index(raw_date),
            end=note.index(raw_date) + len(raw_date),
            text=raw_date,
            label="DATE",
            source="pyDeid",
            replacement="2011-08-03",
            pydeid_types=["Day Month Year (2) [dd of Month, yy(yy)]"],
            metadata={},
        )
    ]

    text, final_spans, warnings = reconstruction._reconstruct_with_stable_dates(
        note,
        spans,
        date_shift_offset=1,
        date_shift_days=45,
    )

    assert text == "The patient was admitted on 16 August 2003."
    assert warnings == []
    assert final_spans[0].metadata["replacement_source"] == "project_stable_date_shift"
    assert final_spans[0].metadata["project_date_shift_policy"] == (
        "shifted_day_month_year_natural_language_full_date"
    )

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

def test_stable_date_shift_disabled_partial_natural_date_fallback_is_sanitized():
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

    deidentified_text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
        date_shift_offset=1,
        date_shift_days=45,
        shift_partial_month_day_dates=False,
    )

    warning_text = " ".join(warnings)
    assert deidentified_text == "Approximate partial date <DATE>."
    assert final_spans[0].replacement == "<DATE>"
    assert "Unparseable pyDeid date span" in warning_text
    assert "March 14" not in warning_text
    assert note not in warning_text
