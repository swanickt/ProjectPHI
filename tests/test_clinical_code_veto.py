"""Semantic-preservation tests for compact clinical codes and phrases."""

from project_phi import PHISpan
import project_phi.reconstruction as reconstruction


def _span(note, text, *, label="NAME", replacement="Carter"):
    start = note.index(text)
    return PHISpan(
        start=start,
        end=start + len(text),
        text=text,
        label=label,
        source="pyDeid",
        replacement=replacement,
        pydeid_types=["Last Name (un)"],
        metadata={"pydeid_replacement": replacement},
    )


def test_reconstruction_preserves_gcs_component_score():
    note = "The Glasgow Coma Scale (GCS) of 9 was documented (E2V2M5)."

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [_span(note, "E2V2M5", label="LOCATION", replacement="D8A5K2")],
    )

    assert text == note
    assert warnings == []
    assert spans[0].action == "preserved"
    assert spans[0].metadata["replacement_source"] == "project_clinical_code_veto"
    assert spans[0].metadata["project_clinical_code_context"] == "glasgow_coma_scale"


def test_reconstruction_preserves_tnm_stage():
    note = "Based on TNM staging, the pathological diagnosis was T3N0M0, stage IIA."

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [_span(note, "T3N0M0", label="LOCATION", replacement="G9K0Q8")],
    )

    assert text == note
    assert warnings == []
    assert spans[0].metadata["replacement_source"] == "project_clinical_code_veto"
    assert spans[0].metadata["project_clinical_code_context"] == "tnm_staging"


def test_reconstruction_still_replaces_tnm_shaped_unknown_name_without_context():
    note = "The patient met T3N0M0 yesterday."

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [_span(note, "T3N0M0", label="NAME", replacement="G9K0Q8")],
    )

    assert text == "The patient met G9K0Q8 yesterday."
    assert warnings == []
    assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_preserves_clinical_duration_travel_phrase():
    note = (
        "The patient developed visual disturbances during a 10 days drive "
        "with daily accumulated altitude of 1500 m."
    )

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [_span(note, "10 days drive", label="LOCATION", replacement="171 Hardy Meadow Apt. 924")],
    )

    assert text == note
    assert warnings == []
    assert spans[0].metadata["replacement_source"] == "project_clinical_code_veto"
    assert spans[0].metadata["project_clinical_code_policy"] == (
        "preserved_clinical_duration_phrase"
    )


def test_reconstruction_preserves_contextual_biomedical_abbreviations():
    examples = [
        ("Shiga-like toxin-producing E. coli (STEC) was found in stool.", "STEC"),
        ("The history of Waldenstrom macroglobulinemia (WM) was reviewed.", "WM"),
        ("The EBV-EBER stain was positive in neoplastic cells.", "EBER"),
        ("The sample showed LAMN/HAMN on pathology review.", "HAMN"),
        ("The mutation of GNAS c.602G>A was reported.", "GNAS"),
        ("Ten round ROIs were drawn on the axial image.", "ROIs"),
        ("MDCT showed reduced MR and PH after valve treatment.", "PH"),
        ("JC virus quantitative PCR was positive in CSF.", "JC"),
        ("KEGG pathway enrichment analysis was performed.", "KEGG"),
    ]

    for note, token in examples:
        text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
            note,
            [_span(note, token, label="NAME", replacement="Carter")],
        )

        assert text == note
        assert warnings == []
        assert spans[0].metadata["replacement_source"] == "project_clinical_code_veto"
        assert spans[0].metadata["project_clinical_code_policy"] == (
            "preserved_contextual_clinical_code"
        )


def test_reconstruction_preserves_ordinary_clinical_prose():
    examples = [
        ("Blood pressure is 165/90 mm Hg.", "Blood", "blood_pressure_or_lab_prose"),
        ("Vital signs are normal.", "Vital", "vital_signs_prose"),
        ("Computed tomography revealed torsion.", "Computed", "computed_tomography_prose"),
        ("Computed tomography revealed torsion.", "tomography", "computed_tomography_prose"),
        ("Blood cultures were negative.", "cultures", "culture_prose"),
        ("She was treated with topical antibiotics.", "topical", "treatment_prose"),
        ("The patient returned for follow-up after treatment.", "follow-up", "follow_up_prose"),
        ("A well-child examination was completed.", "well-child", "well_child_prose"),
        ("He reported chronic left-sided pain.", "left-sided", "laterality_prose"),
        ("The diagnosis was low-risk MDS.", "low-risk", "risk_status_prose"),
        ("She presented for a pre-employment examination.", "pre-employment", "exam_context_prose"),
        ("The chest tube was clamped.", "clamped", "procedure_prose"),
        ("The general practitioners reviewed the case.", "general", "clinical_role_prose"),
    ]

    for note, token, context_name in examples:
        text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
            note,
            [_span(note, token, label="NAME", replacement="Carter")],
        )

        assert text == note
        assert warnings == []
        assert spans[0].metadata["replacement_source"] == "project_ordinary_clinical_prose_veto"
        assert spans[0].metadata["project_ordinary_clinical_prose_context"] == context_name


def test_reconstruction_does_not_preserve_ordinary_clinical_word_without_context():
    note = "Blood attended the visit."

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [_span(note, "Blood", label="NAME", replacement="Carter")],
    )

    assert text == "Carter attended the visit."
    assert warnings == []
    assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_preserves_vendor_reference_metadata_without_geography():
    examples = [
        ("Treatment used TrueBeam by Varian Medical Systems.", "Varian"),
        ("PCR used a Clonit Srl assay.", "Srl"),
        ("Sequencing was performed at Caris Life Science Laboratory.", "Caris"),
        ("Testing used the PowerPlex kit from Promega.", "Promega"),
        ("The patient received Mucosta from Otsuka Pharmaceutical.", "Otsuka"),
        ("Drainage used a MERA system from Senko Medical.", "Senko"),
        ("MALDI-TOF used the Bruker database.", "Bruker"),
        ("IHC used Clone E29 from Dako.", "Dako"),
        ("Blood cultures were tested by Vitek MS.", "Vitek"),
        ("An esophageal ELLA prosthesis was placed.", "ELLA"),
        ("Dental restoration used 3M ESPE.", "ESPE"),
        ("Dental restoration used 3 M ESPE.", "ESPE"),
        ("A Biosense Webster ablation catheter was used.", "Webster"),
        ("The Biosense Webster catheter is made by Johnson & Johnson Medical.", "Johnson"),
        ("The Prolene suture was from Johnson & Johnson.", "Johnson"),
    ]

    for note, token in examples:
        text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
            note,
            [_span(note, token, label="NAME", replacement="Carter")],
        )

        assert text == note
        assert warnings == []
        assert spans[0].metadata["replacement_source"] == "project_clinical_code_veto"
        assert spans[0].metadata["project_clinical_code_policy"] == (
            "preserved_vendor_reference_metadata"
        )


def test_reconstruction_does_not_preserve_vendor_geography_name():
    note = "The device was manufactured in Milan, Italy."

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [_span(note, "Milan", label="LOCATION", replacement="Toronto")],
    )

    assert text == "The device was manufactured in Toronto, Italy."
    assert warnings == []
    assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_does_not_preserve_vendor_like_person_names_without_context():
    examples = [
        ("Webster attended the clinic visit.", "Webster"),
        ("Johnson attended the clinic visit.", "Johnson"),
    ]

    for note, token in examples:
        text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
            note,
            [_span(note, token, label="NAME", replacement="Carter")],
        )

        assert text == "Carter attended the clinic visit."
        assert warnings == []
        assert spans[0].metadata["replacement_source"] == "pyDeid"
