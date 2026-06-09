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


def _offset_span(note, text, start, *, label="ID", replacement="844-555-1212"):
    return PHISpan(
        start=start,
        end=start + len(text),
        text=text,
        label=label,
        source="pyDeid",
        replacement=replacement,
        pydeid_types=["Telephone/Fax", "SIN"],
        metadata={"pydeid_replacement": replacement},
    )


def test_reconstruction_prunes_overlapping_spans_inside_genomic_coordinates():
    note = (
        "DECIPHER reported a pathogenic sequence variant "
        "(1:187074685-248262713) and additional alteration "
        "chr8:141415657-146174033 in genomic context."
    )
    first = note.index("1:187074685")
    second = note.index("187074685-2482")
    third = note.index("074685-248262713")
    fourth = note.index("8:141415657")
    fifth = note.index("141415657-1461")
    spans = [
        _offset_span(note, "1:187074685", first, label="TIME", replacement="8:8:00"),
        _offset_span(note, "187074685-2482", second),
        _offset_span(note, "074685-248262713", third),
        _offset_span(note, "8:141415657", fourth, label="TIME", replacement="8:8:00"),
        _offset_span(note, "141415657-1461", fifth),
    ]

    text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert text == note
    assert final_spans == []
    assert warnings == [
        "pyDeid span inside genomic coordinate dropped during reconstruction.",
        "pyDeid span inside genomic coordinate dropped during reconstruction.",
        "pyDeid span inside genomic coordinate dropped during reconstruction.",
        "pyDeid span inside genomic coordinate dropped during reconstruction.",
        "pyDeid span inside genomic coordinate dropped during reconstruction.",
    ]


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
        ("ASMA antibodies were positive for anti-smooth muscle antibody.", "ASMA"),
        ("The tumor had FUHRMAN nuclear grade 2 on pathology review.", "FUHRMAN"),
        ("Allred proportion score was recorded for ER expression.", "Allred"),
        ("Typus intestinalis sec. Lauren was noted in the gastric tumor.", "Lauren"),
        ("Histologic type by Lauren was diffuse.", "Lauren"),
        ("The patient underwent hemicolectomy.", "hemi"),
        ("The procedure was hemithyroidectomy.", "hemi"),
        ("The patient underwent left hemi-colectomy.", "hemi"),
        ("The patient underwent right hemi-hepatectomy.", "hemi"),
        ("L3-L4 hemi-laminectomy was performed.", "hemi"),
        ("The specimen was right hemi-thyroidectomy.", "hemi"),
        ("The mass involved the right hemi-scrotum.", "hemi"),
        ("The patient underwent hemi-maxillectomy.", "hemi"),
        ("The loop was fixed in the right hemi-pelvis.", "hemi"),
        ("The x-ray showed hemi-vertebrae at T6.", "hemi"),
        ("The MRI showed a divided hemi-cord.", "hemi"),
        ("The CT showed right hemi-thorax opacification.", "hemi"),
        ("The tumor involved the left hemi-trigone.", "hemi"),
        ("The chart noted hemi-CRVO.", "hemi"),
        ("The patient had hemifacial spasm.", "hemi"),
        ("ASMA, AMA, and anti-LKM-1 antibodies were negative for auto-immune hepatitis.", "ASMA"),
        ("Negative stains include ASMA and desmin.", "ASMA"),
        ("Special Stain listed NEG-HER2 and IMM RECUT.", "IMM"),
        ("The block map listed AXT axillary tail site.", "AXT"),
        ("Cytokeratin Cocktail (KER) was ordered.", "KER"),
        ("MAK-6, EMA, and Desmin were negative.", "MAK"),
        ("The lymphocyte count included LYM% of 5.20%.", "LYM"),
        ("Frozen Section Pathologist reviewed FS B1.", "FS"),
        ("The upper renal artery (URA) was aneurysmal.", "URA"),
        ("Date Coll: specimen was collected in formalin.", "Coll"),
        ("COLL. TIME IN FORMALIN: 6:29 hrs.", "COLL"),
        ("Provider Group: Grou was present in the pathology report.", "Grou"),
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
        ("GROSS DESCRIPTION: The specimen was received in formalin.", "GROSS", "pathology_report_header_prose"),
        ("FINAL DIAGNOSIS: invasive ductal carcinoma.", "DIAGNOSIS", "pathology_report_header_prose"),
        ("REVISED DIAGNOSIS: invasive ductal carcinoma.", "DIAGNOSIS", "pathology_report_header_prose"),
        ("Permanent Diagnosis: same.", "Diagnosis", "pathology_report_header_prose"),
        ("Surgical Pathology Report documented the biopsy.", "Pathology", "pathology_report_header_prose"),
        ("This case was reviewed by the Pathology Service.", "Pathology", "pathology_report_header_prose"),
        ("CLINICAL HISTORY: breast cancer.", "CLINICAL", "pathology_report_header_prose"),
        ("CLINICAL HISTORY: breast cancer.", "HISTORY", "pathology_report_header_prose"),
        ("MICROSCOPIC DESCRIPTION: sections show carcinoma.", "MICROSCOPIC", "pathology_report_header_prose"),
        ("Microscopic/Diagnostic Dictation: Pathologist.", "Microscopic", "pathology_report_header_prose"),
        ("SURGICAL MARGINS: uninvolved by tumor.", "SURGICAL", "pathology_report_header_prose"),
        ("SURGICAL PATHOL Report was reviewed.", "SURGICAL", "pathology_report_header_prose"),
        ("ADDENDUM REPORT: immunostains are reported.", "ADDENDUM", "pathology_report_header_prose"),
        ("ADDENDUM: ONCOTYPE DX BREAST CANCER ASSAY.", "ADDENDUM", "pathology_report_header_prose"),
        ("COMMENT: The tumor was reviewed.", "COMMENT", "pathology_report_header_prose"),
        ("Specimen Size: 4.5 cm.", "Specimen", "pathology_report_header_prose"),
        ("Specimen B is received fresh and labeled right breast.", "Specimen", "pathology_report_header_prose"),
        ("Margins involved by invasive carcinoma were absent.", "Margins", "pathology_report_header_prose"),
        ("Deep margin negative for carcinoma.", "margin", "pathology_report_header_prose"),
        ("FINAL PATHOLOGIC DIAGNOSIS: carcinoma.", "FINAL", "pathology_report_header_prose"),
        ("Tumor size: 2.0 cm.", "Tumor", "pathology_report_header_prose"),
        ("Intraoperative Consultation with frozen section was performed.", "Consultation", "pathology_report_header_prose"),
        ("Intraoperative Consultation with frozen section was performed.", "Intraoperative", "pathology_report_header_prose"),
        ("Medical Record review was completed.", "Record", "medical_record_prose"),
        ("Results were reported to the Physician of Record.", "Record.", "medical_record_prose"),
        ("At follow-up, her mRS score was 4.", "score", "clinical_score_prose"),
        ("The NIHSS score was 21.", "score", "clinical_score_prose"),
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
        ("FISH images were reviewed on a Carl Zeiss microscope.", "Zeiss"),
        ("FISH used a modified Vysis protocol.", "Vysis"),
        ("The da Vinci Surgical System was used for robotic surgery.", "Vinci"),
        ("A Stryker Trevo device was used for thrombectomy.", "Stryker"),
        ("The aneurysm was embolized with Stryker coils.", "Stryker"),
        ("A Trident acetabular cup from Stryker was inserted.", "Stryker"),
        ("A Gamma3 intramedullary nail from Stryker was inserted.", "Stryker"),
        ("The Stryker pressure monitor measured compartment pressure.", "Stryker"),
        ("A Zimmer Biomet implant was placed.", "Zimmer"),
        ("CollaTape was obtained from Zimmer Dental Inc.", "Zimmer"),
        ("Somanetics INVOS oximeter monitoring was used.", "Somanetics"),
        ("The Mayfield skull clamp was applied.", "Mayfield"),
        ("The head was placed in a Mayfield holder.", "Mayfield"),
        ("Mayfield frame application was performed.", "Mayfield"),
        ("Bayer contrast was administered.", "Bayer"),
        ("Baytril from Bayer Animal Health was prescribed.", "Bayer"),
        ("The Centaur assay platform from Bayer was used.", "Bayer"),
        ("Advantix spot-on from Bayer AG was applied.", "Bayer"),
        ("Hema-tek 2000 from Bayer was used for staining.", "Bayer"),
        ("The Tomey corneal topographer was used.", "Tomey"),
        ("Cell Marque antibodies were used for immunohistochemical staining.", "Marque"),
        ("A Lacrosse balloon catheter from Goodman was used.", "Goodman"),
        ("Philips Ingenuity CT simulation scanner was used.", "Philips"),
        ("The Zeiss Cirrus HD-OCT 5000 demonstrated thickening.", "Zeiss"),
        ("Symphony 1.5T Siemens MRI demonstrated atrophy.", "Siemens"),
        ("A Stryker Excelsior XT-27 microcatheter was advanced.", "Stryker"),
        ("Perclose Pro-Glide SMC from Abbott was deployed.", "Abbott"),
        ("The patient received atezolizumab from Hoffmann-La Roche AG.", "Roche"),
        ("Drontal Plus tablets from Bayer were prescribed.", "Bayer"),
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


def test_reconstruction_does_not_preserve_ura_inside_larger_word():
    note = "The durable implant was documented after renal imaging."
    start = note.index("ura")
    span = PHISpan(
        start=start,
        end=start + 3,
        text="URA",
        label="NAME",
        source="pyDeid",
        replacement="Carter",
        pydeid_types=["Last Name (un)"],
        metadata={"pydeid_replacement": "Carter"},
    )

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
    )

    assert text == "The dCarterble implant was documented after renal imaging."
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
            "Allred attended the visit.",
            "Allred",
            "Carter attended the visit.",
        ),
        (
            "Lauren attended the visit.",
            "Lauren",
            "Carter attended the visit.",
        ),
        (
            "ASMA attended the visit.",
            "ASMA",
            "Carter attended the visit.",
        ),
        (
            "GROSS attended the visit.",
            "GROSS",
            "Carter attended the visit.",
        ),
        (
            "Zeiss attended the visit.",
            "Zeiss",
            "Carter attended the visit.",
        ),
        (
            "Mayfield attended the visit.",
            "Mayfield",
            "Carter attended the visit.",
        ),
        (
            "Philips attended the visit.",
            "Philips",
            "Carter attended the visit.",
        ),
        (
            "Clinical attended the visit.",
            "Clinical",
            "Carter attended the visit.",
        ),
        (
            "Specimen attended the visit.",
            "Specimen",
            "Carter attended the visit.",
        ),
        (
            "Goodman attended the visit.",
            "Goodman",
            "Carter attended the visit.",
        ),
        (
            "Marque attended the visit.",
            "Marque",
            "Carter attended the visit.",
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
