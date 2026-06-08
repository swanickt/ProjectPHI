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
        ("HER2-", "receptor_and_biomarker_status"),
        ("Ki-67 index", "receptor_and_biomarker_status"),
        ("cT2N1M0", "staging_recurrence_metastasis"),
        ("T3N0M0", "staging_recurrence_metastasis"),
        ("clinical and radiographic remission", "remission_disease_status"),
        ("atypical ductal hyperplasia", "breast_cancer_pathology"),
        ("lymphovascular invasion", "breast_cancer_pathology"),
        ("negative margin", "breast_cancer_pathology"),
        ("dose-dense AC-T", "treatment_surgery_radiation"),
        ("sentinel lymph node dissection", "treatment_surgery_radiation"),
        ("trastuzumab", "treatment_surgery_radiation"),
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
        "iRECIST",
        "CTCAE grade",
        "NIA-AA criteria",
        "New York Heart Association",
        "JOA score",
        "Fazekas grade",
        "Oldenburg Sentence Test",
        "Hamilton Anxiety Scale",
        "Hamilton Depression Scale",
        "Hamilton Depression Rating Scale",
        "Hamilton Rating Scale for Depression",
        "Chelsea Critical Care Physical Assessment Tool",
        "Paddick gradient index",
        "Paddick index",
        "SAFA-A",
        "dose-volume histogram",
        "calcifications",
        "radiation boost",
        "Merkel cell carcinoma",
        "myasthenia gravis",
        "follow-up",
        "homecare",
        "low-income",
        "left-sided",
        "do-not-resuscitate",
        "diabetes mellitus",
        "major depressive disorder",
        "lumbar puncture",
        "de novo",
        "de-escalation",
        "de-clamped",
        "Vo thalamotomy",
        "Jackson Pratt drain",
        "Jackson-Pratt drain",
        "Jackson-Pratt (JP) drain",
        "Bruner incisions",
        "Pfannenstiel incision",
        "Langhans giant cells",
        "Langhans multinucleated giant cells",
        "McFarland standard",
        "0.5 McFarland",
        "et al.",
        "Corman et al.",
        "in situ",
        "ex vivo",
        "in silico",
        "status post",
        "hemi-abdomen",
        "dermo-hypodermal",
        "Heiner syndrome",
        "P. insidiosum",
        "Endo-GIA",
        "Sof-lex/3 M ESPE",
        "anti-aminoacyl-transfer RNA synthetase",
        "Bruton tyrosine kinase",
        "Grover disease",
        "Johanson-Blizzard syndrome",
        "Grocott methenamine silver",
        "Fogarty vascular-clamp forceps",
        "Janeway lesions",
        "Hampton's Hump",
        "NeuN",
        "Volante et al.",
        "Kocher-Langenbach approach",
        "Ramirez technique",
        "veno-occlusive disease",
        "Harrington test",
        "livor mortis",
        "Samii T2",
        "Zhong Wan",
        "Zhong Ting",
        "cun",
        "Standford type A",
        "factor XIII",
        "von Willebrand factor antigen",
        "whole exome sequencing",
        "Replogle tube",
        "von Hippel-Lindau syndrome",
        "Li-Fraumeni syndrome",
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


def test_builtin_component_extensions_preserve_observed_tool_fragments_in_phrase_context():
    examples = [
        ("The Wieneke index score was zero.", "Wieneke"),
        ("The Fazekas scale score was mild.", "Fazekas"),
        ("The Oldenburg Sentence Test was repeated.", "Oldenburg"),
        ("The New York Heart Association class was documented.", "York"),
        ("The Hamilton Anxiety Scale score was high.", "Hamilton"),
        ("The Hamilton Depression Scale score was elevated.", "Hamilton"),
        ("The Hamilton Depression Rating Scale score was elevated.", "Hamilton"),
        ("A lumbar puncture was performed.", "lumbar"),
        ("A Replogle tube was placed.", "Replogle"),
        ("The diagnosis was Merkel cell carcinoma.", "Merkel"),
        ("Symptoms reflected myasthenia gravis.", "gravis"),
        ("The Paddick gradient index was reported.", "Paddick"),
        ("The Paddick index was reported.", "Paddick"),
        ("The SAFA-A questionnaire was administered.", "SAFA"),
        ("This was de novo metastatic melanoma.", "novo"),
        ("This was de novo metastatic melanoma.", "de"),
        ("de-escalation of vasopressors occurred.", "de"),
        ("Vasopressors underwent de-escalation.", "escalation"),
        ("de-adaptation of short bowel syndrome was likely.", "de"),
        ("The tube was de-clamped.", "de"),
        ("The patient underwent Vo thalamotomy.", "Vo"),
        ("Bilateral lesions covered the Vo and ventral intermediate nuclei.", "Vo"),
        ("A Jackson Pratt drain was placed.", "Jackson"),
        ("A Jackson Pratt drain was placed.", "Pratt"),
        ("A Jackson-Pratt drain was placed.", "Jackson"),
        ("A Jackson-Pratt drain was placed.", "Pratt"),
        ("A Jackson-Pratt (JP) drain was placed.", "Jackson"),
        ("A Jackson-Pratt (JP) drain was placed.", "Pratt"),
        ("Bruner incisions were used.", "Bruner"),
        ("A Pfannenstiel incision was made.", "Pfannenstiel"),
        ("Biopsy showed Langhans giant cells.", "Langhans"),
        ("Biopsy showed Langhans multinucleated giant cells.", "Langhans"),
        ("The inoculum used a McFarland standard.", "McFarland"),
        ("The inoculum was 0.5 McFarland.", "McFarland"),
        ("The authors et al. reported toxicity.", "al"),
        ("The authors et al reported toxicity.", "al"),
        ("Corman et al. described the technique.", "Corman"),
        ("Volante et al. described the staining score.", "Volante"),
        ("Tumor was carcinoma in situ.", "situ"),
        ("Cells were studied ex vivo.", "ex"),
        ("Cells were studied ex vivo.", "vivo"),
        ("Support used veno-venous extracorporeal membrane oxygenation.", "veno"),
        ("Support used veno-venous ECMO.", "veno"),
        ("He had blunt trauma to the left hemi-abdomen.", "hemi"),
        ("The diagnosis was Heiner syndrome.", "Heiner"),
        ("Biopsy showed dermo-hypodermal tumor proliferation.", "dermo"),
        ("Culture grew P. insidiosum.", "P."),
        ("Culture grew P. insidiosum.", "insidiosum"),
        ("The device fired an Endo-GIA stapler.", "GIA"),
        ("Dental polishing used Sof-lex/3 M ESPE discs.", "M"),
        ("The antibodies were anti-aminoacyl-transfer RNA synthetase antibodies.", "anti-aminoacyl-transfer"),
        ("Treatment used a Bruton tyrosine kinase inhibitor.", "Bruton"),
        ("The differential included Grover disease.", "Grover"),
        ("Testing suggested Johanson-Blizzard syndrome.", "Johanson"),
        ("Testing suggested Johanson-Blizzard syndrome.", "Blizzard"),
        ("Grocott methenamine silver stains were negative.", "Grocott"),
        ("A Fogarty vascular-clamp forceps was used.", "Fogarty"),
        ("The skin exam showed Janeway lesions.", "Janeway"),
        ("Imaging was consistent with Hampton's Hump.", "Hampton"),
        ("The Kocher-Langenbach approach was used.", "Kocher"),
        ("The Kocher-Langenbach approach was used.", "Langenbach"),
        ("The Ramirez technique was performed.", "Ramirez"),
        ("Concern was raised for veno-occlusive disease.", "veno"),
        ("The Harrington test was positive.", "Harrington"),
        ("Autopsy showed livor mortis.", "mortis"),
        ("The tumor was classified as Samii T2.", "Samii"),
        ("The points included Zhong Wan.", "Zhong"),
        ("The points included Zhong Ting.", "Zhong"),
        ("The diagnosis was Standford type A acute aortic dissection.", "Standford"),
        ("The x-ray showed a raised left hemi-diaphragm.", "hemi"),
        ("Factor XIII activity was checked.", "XIII"),
        ("The syndrome was von Hippel-Lindau disease.", "von"),
        ("Testing included von Willebrand factor antigen.", "von"),
        ("Testing included von Willebrand factor antigen.", "Willebrand"),
        ("The syndrome was Li-Fraumeni syndrome.", "Li"),
    ]

    for note, token in examples:
        start = note.index(token)
        span = _span(token, start=start)

        text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
            note,
            [span],
            protected_terms_profile=_builtin_profile(),
        )

        assert warnings == []
        assert text == note
        assert spans[0].action == "preserved"
        assert spans[0].metadata["replacement_source"] == "project_protected_clinical_term"
        assert spans[0].metadata["project_protected_term_policy"] == (
            "exact_normalized_component_within_phrase"
        )


def test_builtin_component_extensions_do_not_preserve_risky_tokens_globally():
    examples = [
        ("Wieneke attended the visit.", "Wieneke"),
        ("Fazekas called the clinic.", "Fazekas"),
        ("Oldenburg clinic called.", "Oldenburg"),
        ("Hamilton attended the visit.", "Hamilton"),
        ("Replogle signed the form.", "Replogle"),
        ("Merkel attended the visit.", "Merkel"),
        ("Novo attended the visit.", "Novo"),
        ("De attended the visit.", "De"),
        ("Al attended the visit.", "Al"),
        ("Corman attended the visit.", "Corman"),
        ("Von attended the visit.", "Von"),
        ("Veno attended the visit.", "Veno"),
        ("Hemi attended the visit.", "Hemi"),
        ("Heiner attended the visit.", "Heiner"),
        ("Dermo attended the visit.", "Dermo"),
        ("SAFA attended the visit.", "SAFA"),
        ("Paddick attended the visit.", "Paddick"),
        ("York attended the visit.", "York"),
        ("Vo attended the visit.", "Vo"),
        ("Jackson attended the visit.", "Jackson"),
        ("Pratt attended the visit.", "Pratt"),
        ("Bruner attended the visit.", "Bruner"),
        ("Pfannenstiel attended the visit.", "Pfannenstiel"),
        ("Langhans attended the visit.", "Langhans"),
        ("McFarland attended the visit.", "McFarland"),
        ("P. attended the visit.", "P."),
        ("GIA attended the visit.", "GIA"),
        ("M attended the visit.", "M"),
        ("XIII attended the visit.", "XIII"),
        ("Willebrand attended the visit.", "Willebrand"),
    ]

    for note, token in examples:
        start = note.index(token)
        span = _span(token, start=start)

        text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(
            note,
            [span],
            protected_terms_profile=_builtin_profile(),
        )

        assert spans[0].action == "replaced"
        assert spans[0].replacement == "Carter"
        assert token not in text
