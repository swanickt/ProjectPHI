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
        ("The fetal chromosome karyotype was 46, XY, del (18).", "XY"),
        ("The fetal chromosome karyotype was 46, XY, del (18).", "del"),
        ("A standard Brockenbrough needle was used for transseptal access.", "Brock"),
        ("Bilateral lesions covered the Vo and ventral intermediate nuclei.", "Vo"),
        (
            "CGH array showed arr 1q22q25.1 (154559773-171639287,) X1.",
            "559773-171639287",
        ),
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
        ("He returned for a follow-up examination.", "follow-up", "follow_up_prose"),
        ("A clinic for low-income residents provided care.", "low-income", "social_context_prose"),
        ("Homecare staff helped with medications.", "Homecare", "care_context_prose"),
        ("MR imaging findings suggested demyelination.", "findings", "imaging_findings_prose"),
        ("She was treated by a practitioner with topical antibiotics.", "with", "treatment_prose"),
        ("MDCT showed resolution of HALT and RLM after treatment.", "and", "cardiology_or_abbreviation_prose"),
        ("Prior to the accident, he drank beer daily.", "Prior", "temporal_prose"),
        ("He came to the physician in December for episodic shortness of breath.", "December", "month_reference_prose"),
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


def test_reconstruction_does_not_preserve_long_numeric_range_without_genomic_context():
    note = "The patient had identifier 559773-171639287 in the source system."

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [_span(note, "559773-171639287", label="ID", replacement="844-415-6485")],
    )

    assert text == "The patient had identifier 844-415-6485 in the source system."
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
        ("Isolates were identified using the VITEK 2 system.", "VITEK"),
        ("A SOFIA catheter from MicroVention was advanced.", "SOFIA"),
        ("ICP-MS used the Varian 810-MS platform.", "Varian"),
        ("Samples were collected in Streck DNA BCT tubes.", "Streck"),
        ("The cfDNA profile was checked on an Agilent Bioanalyzer.", "Agilent"),
        ("A 29 mm Edwards Sapien 3 valve was placed.", "Sapien"),
        ("Drainage used the MERA Sacuum suction unit.", "MERA"),
        ("Direct dental composite restorations used Herculite Kerr.", "Kerr"),
        ("Rigorous polishing used a Kulzer tool kit.", "Kulzer"),
        ("The Smith & Nephew RENASYS system was used.", "Smith"),
        ("Monitoring used the PetMAP Ramsey system.", "Ramsey"),
        ("FISH signals were analyzed with a Zeiss Axioplan microscope.", "Zeiss"),
        ("FISH used a modified Vysis protocol.", "Vysis"),
        ("The da Vinci Surgical System was used for robotic surgery.", "Vinci"),
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


def test_reconstruction_preserves_cun_only_in_acupuncture_measurement_context():
    note = "The needles were inserted to a depth of 0.2 cun."

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [_span(note, "cun", label="NAME", replacement="Carter")],
    )

    assert text == note
    assert warnings == []
    assert spans[0].metadata["replacement_source"] == "project_clinical_code_veto"
    assert spans[0].metadata["project_clinical_code_policy"] == (
        "preserved_contextual_clinical_code"
    )
    assert spans[0].metadata["project_clinical_code_context"] == (
        "acupuncture_measurement"
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
        ("Webster attended the clinic visit.", "Webster", "Carter attended the clinic visit."),
        ("Johnson attended the clinic visit.", "Johnson", "Carter attended the clinic visit."),
        ("Smith attended the clinic visit.", "Smith", "Carter attended the clinic visit."),
        ("Ramsey attended the clinic visit.", "Ramsey", "Carter attended the clinic visit."),
        (
            "Smith changed the wound VAC dressing.",
            "Smith",
            "Carter changed the wound VAC dressing.",
        ),
        (
            "Ramsey checked the blood pressure device.",
            "Ramsey",
            "Carter checked the blood pressure device.",
        ),
        (
            "The source system recorded cun as a label.",
            "cun",
            "The source system recorded Carter as a label.",
        ),
    ]

    for note, token, expected_text in examples:
        text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
            note,
            [_span(note, token, label="NAME", replacement="Carter")],
        )

        assert text == expected_text
        assert warnings == []
        assert spans[0].metadata["replacement_source"] == "pyDeid"
