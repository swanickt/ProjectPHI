"""Protected clinical terminology tests using synthetic examples only."""

from project_phi import PHISpan, deidentify_note
import project_phi.reconstruction as reconstruction
from project_phi.protected_terms import _build_protected_terms_profile


def _span(text, *, start=4, replacement="Carter"):
    return PHISpan(
        start=start,
        end=start + len(text),
        text=text,
        label="NAME",
        source="pyDeid",
        replacement=replacement,
        pydeid_types=["Last Name (STitle)"],
        metadata={
            "pydeid_replacement": replacement,
            "pydeid_surrogate_start": 4,
            "pydeid_surrogate_end": 10,
        },
    )


def _profile(terms=None):
    return _build_protected_terms_profile(
        terms
        or {
            "synthetic_breast_imaging": {
                "category": "breast_imaging_mammography",
                "terms": ["tomosynthesis", "mammography with tomosynthesis"],
            }
        },
        include_builtin_protected_clinical_terms=False,
    )


def _clinical_tool_profile():
    return _build_protected_terms_profile(
        {
            "synthetic_clinical_tools": {
                "category": "clinical_tools_scales_criteria",
                "terms": ["JOA score", "Fazekas grade"],
                "component_terms": [
                    {
                        "component": "Chelsea",
                        "within_phrase": "Chelsea Critical Care Physical Assessment Tool",
                    },
                    {"component": "Wieneke", "within_phrase": "Wieneke criteria"},
                ],
            }
        },
        include_builtin_protected_clinical_terms=False,
    )


def _builtin_profile():
    return _build_protected_terms_profile(
        None,
        include_builtin_protected_clinical_terms=True,
    )


def test_reconstruction_preserves_exact_protected_clinical_term_span():
    note = "Dr. Tomosynthesis reviewed."
    span = _span("Tomosynthesis")

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        protected_terms_profile=_profile(),
    )

    protected_span = spans[0]
    assert text == note
    assert warnings == []
    assert protected_span.action == "preserved"
    assert protected_span.replacement == "Tomosynthesis"
    assert protected_span.metadata["replacement_source"] == "project_protected_clinical_term"
    assert protected_span.metadata["project_protected_term_policy"] == "exact_normalized_span_match"
    assert protected_span.metadata["project_protected_term_rule_id"] == "synthetic_breast_imaging"
    assert protected_span.metadata["project_protected_term_category"] == "breast_imaging_mammography"
    assert "pydeid_replacement" in protected_span.metadata
    assert "pydeid_surrogate_start" in protected_span.metadata
    assert "pydeid_surrogate_end" in protected_span.metadata
    assert note[protected_span.start : protected_span.end] == protected_span.text
    project_start = protected_span.metadata["project_replacement_start"]
    project_end = protected_span.metadata["project_replacement_end"]
    assert text[project_start:project_end] == protected_span.replacement


def test_protected_term_matching_is_case_and_whitespace_normalized():
    note = "Dr.   TOMOSYNTHESIS, reviewed."
    span = _span("  TOMOSYNTHESIS, ", start=3)

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        protected_terms_profile=_profile(),
    )

    assert spans[0].action == "preserved"
    assert spans[0].replacement == "  TOMOSYNTHESIS, "
    assert spans[0].metadata["replacement_source"] == "project_protected_clinical_term"
    assert spans[0].metadata["project_protected_term_policy"] == "exact_normalized_span_match"
    assert spans[0].metadata["project_protected_term_rule_id"] == "synthetic_breast_imaging"
    assert "TOMOSYNTHESIS" in text


def test_protected_term_matching_does_not_match_substrings():
    note = "Dr. Screening tomosynthesis reviewed."
    span = _span("Screening tomosynthesis")

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        protected_terms_profile=_profile(),
    )

    assert spans[0].action == "replaced"
    assert spans[0].replacement == "Carter"
    assert text == "Dr. Carter reviewed."


def test_unknown_name_span_still_uses_pydeid_replacement():
    note = "Dr. Xavion reviewed."
    span = _span("Xavion")

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        protected_terms_profile=_profile(),
    )

    assert spans[0].action == "replaced"
    assert spans[0].replacement == "Carter"
    assert text == "Dr. Carter reviewed."


def test_builtin_extensions_preserve_high_value_breast_oncology_terms():
    examples = [
        ("bilateral digital mammography with tomosynthesis", "breast_imaging_mammography"),
        ("post-lumpectomy changes", "breast_imaging_mammography"),
        ("no suspicious sonographic abnormality", "breast_imaging_findings"),
        ("ER+/PR+/HER2-", "receptor_and_biomarker_status"),
        ("cT2N1M0", "staging_recurrence_metastasis"),
        ("clinical and radiographic remission", "remission_disease_status"),
        ("dose-dense AC-T", "treatment_surgery_radiation"),
        ("DEXA scan", "systemic_endocrine_therapy"),
    ]

    for term, category in examples:
        note = f"Dr. {term} reviewed."
        span = _span(term)

        text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
            note,
            [span],
            protected_terms_profile=_builtin_profile(),
        )

        protected_span = spans[0]
        assert warnings == []
        assert text == note
        assert protected_span.action == "preserved"
        assert protected_span.replacement == term
        assert protected_span.metadata["replacement_source"] == "project_protected_clinical_term"
        assert protected_span.metadata["project_protected_term_category"] == category
        assert protected_span.metadata["project_protected_term_policy"] == (
            "exact_normalized_span_match"
        )


def test_builtin_extensions_still_require_exact_whole_span_match():
    note = "Dr. mammogrammer reviewed."
    span = _span("mammogrammer")

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        protected_terms_profile=_builtin_profile(),
    )

    assert spans[0].action == "replaced"
    assert spans[0].replacement == "Carter"
    assert text == "Dr. Carter reviewed."


def test_deidentify_note_preserves_builtin_tomosynthesis_when_pydeid_flags_it():
    note = "Dr. Tomosynthesis reviewed the image."

    result = deidentify_note(note)

    protected_spans = [
        span
        for span in result.spans
        if span.metadata.get("replacement_source") == "project_protected_clinical_term"
    ]
    assert protected_spans
    assert "Tomosynthesis" in result.deidentified_text
    assert protected_spans[0].text == "Tomosynthesis"
    assert protected_spans[0].action == "preserved"


def test_protected_terms_do_not_block_patient_date_or_doctor_replacement():
    note = (
        "Patient Zylanda Qorven saw Dr. Tomosynthesis with Xavion Lorne on "
        "March 14, 2026."
    )

    result = deidentify_note(
        note,
        patient_id="Patient/synth-protected-001",
        stable_patient_name_surrogates=True,
        patient_aliases=["Zylanda Qorven"],
        patient_name_secret="synthetic-name-secret",
        stable_date_shift=True,
        date_shift_secret="synthetic-date-secret",
        custom_dr_first_names={"Xavion"},
        custom_dr_last_names={"Lorne"},
    )

    assert "Tomosynthesis" in result.deidentified_text
    assert "Zylanda" not in result.deidentified_text
    assert "Qorven" not in result.deidentified_text
    assert "Xavion" not in result.deidentified_text
    assert "Lorne" not in result.deidentified_text
    assert "March 14, 2026" not in result.deidentified_text
    assert any(
        span.metadata.get("replacement_source") == "project_protected_clinical_term"
        for span in result.spans
    )
    assert any(
        span.metadata.get("replacement_source") == "project_stable_patient_name"
        for span in result.spans
    )
    assert any(
        span.metadata.get("replacement_source") == "project_stable_date_shift"
        for span in result.spans
    )


def test_protected_component_preserves_tool_name_fragment_only_in_phrase_context():
    note = "The Chelsea Critical Care Physical Assessment Tool score improved."
    span = _span("Chelsea", start=4)

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        protected_terms_profile=_clinical_tool_profile(),
    )

    protected_span = spans[0]
    assert warnings == []
    assert text == note
    assert protected_span.action == "preserved"
    assert protected_span.metadata["replacement_source"] == "project_protected_clinical_term"
    assert protected_span.metadata["project_protected_term_policy"] == (
        "exact_normalized_component_within_phrase"
    )
    assert protected_span.metadata["project_protected_component"] == "chelsea"
    assert protected_span.metadata["project_protected_within_phrase"] == (
        "chelsea critical care physical assessment tool"
    )


def test_protected_component_does_not_preserve_person_like_context():
    note = "Chelsea attended the oncology visit."
    span = _span("Chelsea", start=0)

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        protected_terms_profile=_clinical_tool_profile(),
    )

    assert spans[0].action == "replaced"
    assert spans[0].replacement == "Carter"
    assert text == "Carter attended the oncology visit."


def test_builtin_clinical_tool_terms_include_safe_whole_span_examples():
    examples = [
        "ECOG performance status",
        "Karnofsky Performance Status",
        "RECIST 1.1",
        "CTCAE grade",
        "JOA score",
        "Fazekas grade",
        "Chelsea Critical Care Physical Assessment Tool",
    ]

    for term in examples:
        note = f"The {term} was documented."
        span = _span(term, start=4)

        text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
            note,
            [span],
            protected_terms_profile=_builtin_profile(),
        )

        assert warnings == []
        assert text == note
        assert spans[0].action == "preserved"
        assert spans[0].metadata["replacement_source"] == "project_protected_clinical_term"


def test_builtin_component_protection_does_not_make_risky_token_global():
    note = "Chelsea attended the oncology visit."
    span = _span("Chelsea", start=0)

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        protected_terms_profile=_builtin_profile(),
    )

    assert spans[0].action == "replaced"
    assert spans[0].replacement == "Carter"
    assert text == "Carter attended the oncology visit."
