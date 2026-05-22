"""Synthetic end-to-end tests for PHI removal and semantic preservation.

These tests exercise the public ProjectPHI API as a small synthetic evaluation
suite. They intentionally combine multiple policy layers instead of testing each
helper in isolation.

Main contracts covered:
- raw synthetic names, identifiers, contacts, dates, and aliases are removed from
  de-identified output where expected;
- clinically meaningful surrounding text is preserved;
- stable patient-name replacement applies only to explicit patient aliases;
- unknown names remain pyDeid replacements rather than patient aliases;
- stable date shifting preserves temporal relationships and metadata;
- month/year dates preserve visible month/year granularity;
- protected clinical terms remain available for downstream review;
- custom regex identifiers are replaced without exposing raw regex patterns;
- CSV output preserves successful row shape and omits failed rows;
- audit/warning text avoids raw note text, PHI-like values, aliases, regex
  patterns, secrets, hashes, and HMAC digests.

All names, identifiers, contacts, study tokens, and clinical statements are
synthetic.
"""

from datetime import date

from project_phi import deidentify_csv, deidentify_note
from conftest import _read_csv, _write_csv


DATE_SECRET = "synthetic-date-secret"
NAME_SECRET = "synthetic-name-secret"


def _assert_absent(text, forbidden):
    """Assert that no forbidden synthetic value appears in text.

    Example:
        `_assert_absent(output, ["Zylanda", "2001-04-10"])` verifies that both
        values were removed from the output string.
    """
    for value in forbidden:
        assert value not in text


def _assert_present(text, expected):
    """Assert that every expected clinical/context value appears in text.

    Example:
        `_assert_present(output, ["continue ondansetron", "repeat CBC"])`
        verifies semantic context was preserved.
    """
    for value in expected:
        assert value in text


def _spans_with_text(result, values):
    """Return spans whose original text is one of the supplied values."""
    return [span for span in result.spans if span.text in set(values)]


def _project_spans(result, source):
    """Return spans with a specific ProjectPHI replacement source."""
    return [span for span in result.spans if span.metadata.get("replacement_source") == source]


def _custom_regexes():
    """Return synthetic custom-regex config for end-to-end tests.

    The patterns match fake accession/study-token formats only. They are not
    intended to model real local identifier formats.
    """
    return {
        "synthetic_accession": {
            "phi_type": "Synthetic Accession",
            "pattern": r"\bSYN-ACC-\d{4}\b",
            "replacement": "<SYNTHETIC_ACCESSION>",
        },
        "synthetic_study_token": {
            "phi_type": "Synthetic Study Token",
            "pattern": r"\bSIM-STUDY-\d{3}\b",
            "replacement": "<SYNTHETIC_STUDY_TOKEN>",
        },
    }


def _assert_project_offsets_slice_output(note, result, spans):
    """Assert original offsets and final replacement offsets stay separated.

    For each span:
    - `span.start` / `span.end` must slice the original note;
    - `project_replacement_start` / `project_replacement_end` must slice the
      final de-identified output;
    - pyDeid surrogate offsets must still be preserved in metadata.
    """
    for span in spans:
        assert note[span.start : span.end] == span.text
        project_start = span.metadata["project_replacement_start"]
        project_end = span.metadata["project_replacement_end"]
        assert result.deidentified_text[project_start:project_end] == span.replacement
        assert "pydeid_surrogate_start" in span.metadata
        assert "pydeid_surrogate_end" in span.metadata


# Single-note public workflow scenarios.


def test_single_note_oncology_follow_up_removes_phi_and_preserves_clinical_context():
    """Combined note workflow removes PHI-like values while preserving oncology context."""
    note = (
        "Patient Zylanda Qorven was seen by Dr. Mira Solen on April 10, 2001 at 14:30. "
        "Her sister Amari Qorven reported nausea after cycle 2 chemotherapy. "
        "Dr. Tomosynthesis reviewed mammography with tomosynthesis. "
        "Diagnosis was documented in March 2021 and endocrine therapy started in October 2021. "
        "Plan: continue ondansetron, repeat CBC in 7 days, and review in spring 2001. "
        "Call 416-555-0199 or zylanda.synthetic@example.invalid if symptoms worsen."
    )

    result = deidentify_note(
        note,
        patient_id="Patient/synth-e2e-001",
        stable_date_shift=True,
        date_shift_secret=DATE_SECRET,
        stable_patient_name_surrogates=True,
        patient_aliases=["Zylanda Qorven", "Zylanda"],
        patient_name_secret=NAME_SECRET,
        custom_dr_first_names={"Mira"},
        custom_dr_last_names={"Solen"},
        custom_patient_first_names={"Amari"},
        custom_patient_last_names={"Qorven"},
    )

    _assert_absent(
        result.deidentified_text,
        [
            "Zylanda",
            "Qorven",
            "Dr. Mira",
            "Solen",
            "Amari",
            "April 10, 2001",
            "416-555-0199",
            "zylanda.synthetic@example.invalid",
        ],
    )
    _assert_present(
        result.deidentified_text,
        [
            "nausea after cycle 2 chemotherapy",
            "Tomosynthesis",
            "mammography with tomosynthesis",
            "Diagnosis was documented in",
            "endocrine therapy started in",
            "continue ondansetron",
            "repeat CBC in 7 days",
            "symptoms worsen",
        ],
    )

    patient_spans = _project_spans(result, "project_stable_patient_name")
    assert patient_spans
    for span in patient_spans:
        assert span.metadata["project_name_policy"] == "known_patient_alias"
        assert span.metadata["name_role"] == "known_patient_alias"
        assert span.metadata["alias_match_type"] in {"given", "family", "full"}

    unknown_name_spans = [
        span for span in _spans_with_text(result, {"Mira", "Solen", "Amari"}) if span.label == "NAME"
    ]
    assert unknown_name_spans
    for span in unknown_name_spans:
        assert span.metadata.get("project_name_policy") != "known_patient_alias"
        if "project_name_policy" in span.metadata:
            assert span.metadata["project_name_policy"] == "unknown_name_pydeid"
            assert span.metadata["name_role"] == "unknown_name"

    shifted_date_spans = _project_spans(result, "project_stable_date_shift")
    assert shifted_date_spans
    natural_date_spans = [
        span
        for span in shifted_date_spans
        if span.metadata.get("project_date_shift_policy") == "shifted_natural_language_full_date"
    ]
    assert natural_date_spans
    assert all(span.replacement != "<DATE>" for span in natural_date_spans)

    month_year_spans = [
        span
        for span in shifted_date_spans
        if span.metadata.get("project_date_shift_policy") == "shifted_month_year"
    ]
    assert month_year_spans
    assert all(span.replacement != "<DATE>" for span in month_year_spans)
    assert all(span.metadata["project_date_shift_granularity"] == "month_year" for span in month_year_spans)

    protected_term_spans = _project_spans(result, "project_protected_clinical_term")
    assert protected_term_spans
    assert any(span.text == "Tomosynthesis" for span in protected_term_spans)

    _assert_project_offsets_slice_output(
        note,
        result,
        patient_spans + shifted_date_spans + protected_term_spans,
    )

    # Date-like policy text can be affected by pyDeid detection, so assert the
    # surrounding clinical intent rather than a brittle exact sentence.
    assert "review in" in result.deidentified_text
    warning_text = " ".join(result.warnings)
    _assert_absent(
        warning_text,
        [
            "Zylanda",
            "Qorven",
            "Mira",
            "Solen",
            "Amari",
            "April 10, 2001",
            "March 2021",
            "October 2021",
        ],
    )


def test_copied_correspondence_unknown_names_are_not_patient_aliases_and_clinical_facts_remain():
    """Copied clinician/contact names stay unknown while clinical facts remain."""
    note = (
        "Copied note: Dear Dr. Ivo Laren, Zylanda Qorven attended the clinic. "
        "Original letter from Dr. Rowan Vale also served as the referring contact. "
        "Diagnosis remains asthma exacerbation; oxygen saturation was 94% on room air."
    )

    result = deidentify_note(
        note,
        patient_id="Patient/synth-e2e-001",
        stable_patient_name_surrogates=True,
        patient_aliases=["Zylanda Qorven"],
        patient_name_secret=NAME_SECRET,
        custom_dr_first_names={"Ivo"},
        custom_dr_last_names={"Laren"},
        custom_patient_first_names={"Rowan"},
        custom_patient_last_names={"Vale"},
    )

    _assert_absent(result.deidentified_text, ["Zylanda", "Qorven", "Ivo", "Laren", "Rowan", "Vale"])
    _assert_present(
        result.deidentified_text,
        [
            "Diagnosis remains asthma exacerbation",
            "oxygen saturation was 94% on room air",
        ],
    )

    patient_spans = _project_spans(result, "project_stable_patient_name")
    assert patient_spans
    unknown_spans = [
        span for span in _spans_with_text(result, {"Ivo", "Laren", "Rowan", "Vale"}) if span.label == "NAME"
    ]
    assert unknown_spans
    for span in unknown_spans:
        assert span.metadata.get("project_name_policy") != "known_patient_alias"
        if "project_name_policy" in span.metadata:
            assert span.metadata["project_name_policy"] == "unknown_name_pydeid"
            assert span.metadata["name_role"] == "unknown_name"


def test_date_interval_and_date_like_text_preserve_temporal_and_clinical_meaning():
    """Date shifting preserves intervals while non-shifted date-like context remains meaningful."""
    note = (
        "Started prednisone on 2001-01-05 and stopped on 2001-01-12. "
        "The note references the 2020 guideline, 08:15 vitals, winter symptoms, and stage 2 disease."
    )

    result = deidentify_note(
        note,
        patient_id="Patient/synth-e2e-002",
        stable_date_shift=True,
        date_shift_secret=DATE_SECRET,
    )

    date_spans = [span for span in result.spans if span.label == "DATE" and span.text.startswith("2001-")]
    assert len(date_spans) >= 2
    shifted_dates = [date.fromisoformat(span.replacement) for span in date_spans[:2]]
    original_dates = [date.fromisoformat(span.text) for span in date_spans[:2]]
    assert shifted_dates[1] - shifted_dates[0] == original_dates[1] - original_dates[0]
    assert "2001-01-05" not in result.deidentified_text
    assert "2001-01-12" not in result.deidentified_text

    _assert_present(
        result.deidentified_text,
        [
            "Started prednisone on",
            "and stopped on",
            "guideline",
            "vitals",
            "winter symptoms",
            "stage 2 disease",
        ],
    )

    # Some date-like strings may or may not be detected by pyDeid. When pyDeid
    # does not emit them as spans, the surrounding clinical text should remain.
    detected_text = {span.text for span in result.spans}
    if "2020" not in detected_text:
        assert "2020 guideline" in result.deidentified_text
    if "08:15" not in detected_text:
        assert "08:15 vitals" in result.deidentified_text
    if "winter" not in detected_text:
        assert "winter symptoms" in result.deidentified_text


def test_custom_regex_synthetic_identifiers_are_removed_without_losing_imaging_context():
    """Synthetic custom-regex identifiers are removed while imaging context remains."""
    raw_accession = "SYN-ACC-1234"
    raw_study = "SIM-STUDY-777"
    note = (
        f"Synthetic accession {raw_accession} was reviewed with fake study token {raw_study}. "
        "The CT chest showed no pulmonary embolism and stable 4 mm nodule."
    )

    result = deidentify_note(note, custom_regexes=_custom_regexes())

    _assert_absent(result.deidentified_text, [raw_accession, raw_study])
    _assert_present(
        result.deidentified_text,
        [
            "<SYNTHETIC_ACCESSION>",
            "<SYNTHETIC_STUDY_TOKEN>",
            "no pulmonary embolism",
            "stable 4 mm nodule",
        ],
    )

    custom_spans = [
        span for span in result.spans if span.metadata.get("custom_regex_rule_id") is not None
    ]
    assert {span.metadata["custom_regex_rule_id"] for span in custom_spans} == {
        "synthetic_accession",
        "synthetic_study_token",
    }
    for span in custom_spans:
        assert note[span.start : span.end] == span.text
        assert span.metadata["custom_regex_phi_type"] in span.pydeid_types
        assert r"\bSYN-ACC-" not in str(span.metadata)
        assert r"\bSIM-STUDY-" not in str(span.metadata)


# CSV end-to-end public workflow scenario.


def test_csv_end_to_end_outputs_audit_metadata_and_sanitized_failure(tmp_path):
    """CSV end-to-end run writes good rows, audit metadata, and sanitized row failure."""
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    raw_accession = "SYN-ACC-1234"
    raw_study = "SIM-STUDY-777"
    rows = [
        {
            "patient_id": "Patient/synth-e2e-001",
            "encounter_id": "Encounter/synth-e2e-001a",
            "note_id": "Note/synth-e2e-001a",
            "note_text": (
                "Patient Zylanda Qorven had follow-up on 2001-04-10. "
                "Plan: continue ondansetron and repeat CBC in 7 days."
            ),
            "note_type": "followup",
        },
        {
            "patient_id": "Patient/synth-e2e-001",
            "encounter_id": "Encounter/synth-e2e-001b",
            "note_id": "Note/synth-e2e-001b",
            "note_text": "Started prednisone on 2001-01-05 and stopped on 2001-01-12. Stage 2 disease unchanged.",
            "note_type": "interval",
        },
        {
            "patient_id": "",
            "encounter_id": "Encounter/synth-e2e-fail",
            "note_id": "Note/synth-e2e-fail",
            "note_text": "Patient Vyrella Kade had follow-up on 2001-05-01.",
            "note_type": "failure",
        },
        {
            "patient_id": "Patient/synth-e2e-001",
            "encounter_id": "Encounter/synth-e2e-001c",
            "note_id": "Note/synth-e2e-001c",
            "note_text": (
                f"Synthetic accession {raw_accession} and fake study token {raw_study} reviewed. "
                "The CT chest showed no pulmonary embolism and stable 4 mm nodule."
            ),
            "note_type": "imaging",
        },
    ]
    _write_csv(input_file, rows)

    summary = deidentify_csv(
        input_file,
        output_file,
        audit_output_file=audit_file,
        stable_date_shift=True,
        date_shift_secret=DATE_SECRET,
        stable_patient_name_surrogates=True,
        patient_aliases_by_patient_id={"Patient/synth-e2e-001": ["Zylanda Qorven"]},
        patient_name_secret=NAME_SECRET,
        custom_regexes=_custom_regexes(),
    )

    output_rows = _read_csv(output_file)
    audit_rows = _read_csv(audit_file)
    audit_text = audit_file.read_text(encoding="utf-8")
    summary_warnings = " ".join(summary["warnings"])

    assert summary["rows_read"] == 4
    assert summary["rows_written"] == 3
    assert summary["rows_failed"] == 1
    assert summary["spans_written"] > 0
    assert [row["note_id"] for row in output_rows] == [
        "Note/synth-e2e-001a",
        "Note/synth-e2e-001b",
        "Note/synth-e2e-001c",
    ]
    assert list(output_rows[0]) == list(rows[0])

    output_text = "\n".join(row["note_text"] for row in output_rows)
    _assert_absent(
        output_text,
        [
            "Zylanda",
            "Qorven",
            "Vyrella",
            "Kade",
            "2001-04-10",
            "2001-01-05",
            "2001-01-12",
            "2001-05-01",
            raw_accession,
            raw_study,
        ],
    )
    _assert_present(
        output_text,
        [
            "continue ondansetron",
            "repeat CBC in 7 days",
            "Stage 2 disease unchanged",
            "no pulmonary embolism",
            "stable 4 mm nodule",
        ],
    )

    date_shift_rows = [row for row in audit_rows if row["replacement_source"] == "project_stable_date_shift"]
    assert date_shift_rows
    for row in date_shift_rows:
        assert row["project_date_shift_policy"]
        assert row["project_date_shift_days"]
        assert row["project_date_shift_range_days"] == "45"

    patient_name_rows = [
        row for row in audit_rows if row["replacement_source"] == "project_stable_patient_name"
    ]
    assert patient_name_rows
    for row in patient_name_rows:
        assert row["project_name_policy"] == "known_patient_alias"
        assert row["name_role"] == "known_patient_alias"
        assert row["alias_match_type"] in {"given", "family", "full"}
        assert row["project_replacement_start"]
        assert row["project_replacement_end"]
        assert row["pydeid_replacement"]
        assert row["pydeid_surrogate_start"]
        assert row["pydeid_surrogate_end"]

    custom_rows = [row for row in audit_rows if row["custom_regex_rule_id"] == "synthetic_accession"]
    assert custom_rows
    assert custom_rows[0]["custom_regex_phi_type"] == "Synthetic Accession"
    study_token_rows = [row for row in audit_rows if row["custom_regex_rule_id"] == "synthetic_study_token"]
    assert study_token_rows
    assert study_token_rows[0]["custom_regex_phi_type"] == "Synthetic Study Token"

    warning_rows = [row for row in audit_rows if row["warning"]]
    assert warning_rows
    assert warning_rows[0]["span_index"] == ""
    assert warning_rows[0]["project_name_policy"] == ""
    assert warning_rows[0]["custom_regex_rule_id"] == ""

    # Audit CSVs are internal artifacts and may include fake replacements and
    # offsets, but they must not contain raw note text, raw PHI-like values,
    # raw aliases, raw regex patterns, secrets, hashes, or HMAC digests.
    _assert_absent(
        audit_text,
        [
            rows[0]["note_text"],
            rows[1]["note_text"],
            rows[2]["note_text"],
            rows[3]["note_text"],
            "Zylanda",
            "Qorven",
            "Vyrella",
            "Kade",
            "2001-04-10",
            "2001-01-05",
            "2001-01-12",
            "2001-05-01",
            raw_accession,
            raw_study,
            r"\bSYN-ACC-\d{4}\b",
            r"\bSIM-STUDY-\d{3}\b",
            DATE_SECRET,
            NAME_SECRET,
            "synthetic-date-secret",
            "synthetic-name-secret",
        ],
    )
    _assert_absent(
        summary_warnings,
        [
            rows[2]["note_text"],
            "Vyrella",
            "Kade",
            "2001-05-01",
            DATE_SECRET,
            NAME_SECRET,
        ],
    )
