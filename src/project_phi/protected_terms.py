"""Protected clinical terminology helpers.

Protected terms are semantic-preservation vetoes, not detectors. They are only
matched against pyDeid-emitted spans and never scanned over the full note.
"""

from __future__ import annotations

import re
from typing import Any, Pattern

from .models import PHISpan


_BUILTIN_PROTECTED_CLINICAL_TERMS = {
    "breast_imaging_mammography": {
        "category": "breast_imaging_mammography",
        "terms": [
            "tomosynthesis",
            "mammography",
            "mammography with tomosynthesis",
            "digital mammography",
            "bilateral mammography",
            "screening mammography",
            "diagnostic mammography",
            "surveillance mammography",
            "mammogram",
            "bilateral mammogram",
            "surveillance bilateral mammogram",
            "digital breast tomosynthesis",
            "bilateral digital mammography",
            "bilateral digital mammography with tomosynthesis",
            "mammographic",
            "mammographic finding",
            "mammographic findings",
            "mammographic abnormality",
            "benign mammographic finding",
            "suspicious mammographic finding",
            "post-lumpectomy changes",
            "post treatment changes",
            "post-treatment changes",
            "breast density",
            "dense breast tissue",
            "BI-RADS",
            "BIRADS",
            "BI-RADS 1",
            "BI-RADS 2",
            "BI-RADS 3",
            "BI-RADS 4",
            "BI-RADS 5",
            "BIRADS 1",
            "BIRADS 2",
            "BIRADS 3",
            "BIRADS 4",
            "BIRADS 5",
            "benign findings",
            "probably benign",
            "suspicious abnormality",
            "highly suggestive of malignancy",
            "architectural distortion",
            "pleomorphic calcifications",
            "amorphous calcifications",
            "fine pleomorphic calcifications",
            "linear branching calcifications",
            "segmental calcifications",
        ],
    },
    "breast_imaging_findings": {
        "category": "breast_imaging_findings",
        "terms": [
            "grouped calcifications",
            "coarse calcifications",
            "benign-appearing coarse calcifications",
            "microcalcifications",
            "macrocalcifications",
            "spiculated mass",
            "irregular spiculated mass",
            "breast mass",
            "suspicious mass",
            "no suspicious mass",
            "no suspicious sonographic abnormality",
            "sonographic abnormality",
            "axillary lymph node",
            "abnormal axillary lymph node",
            "skin dimpling",
            "skin thickening",
            "nipple discharge",
            "nipple retraction",
            "retroareolar mass",
            "subareolar mass",
            "upper outer quadrant",
            "left upper outer quadrant",
            "right upper outer quadrant",
            "upper inner quadrant",
            "lower outer quadrant",
            "lower inner quadrant",
        ],
    },
    "breast_cancer_pathology": {
        "category": "breast_cancer_pathology",
        "terms": [
            "ductal carcinoma in situ",
            "invasive ductal carcinoma",
            "invasive ductal carcinoma of the breast",
            "lobular carcinoma in situ",
            "invasive lobular carcinoma",
            "invasive lobular carcinoma of the breast",
            "ductal carcinoma",
            "lobular carcinoma",
            "carcinoma in situ",
            "intermediate-grade ductal carcinoma in situ",
            "high-grade ductal carcinoma in situ",
            "low-grade ductal carcinoma in situ",
            "DCIS",
            "LCIS",
            "IDC",
            "ILC",
            "grade 1",
            "grade 2",
            "grade 3",
            "core biopsy",
            "ultrasound-guided core biopsy",
            "sentinel node biopsy",
            "sentinel lymph node biopsy",
            "lymph node biopsy",
            "nodes positive",
            "node positive",
            "sentinel lymph node",
            "micrometastasis",
            "micrometastases",
            "macrometastasis",
            "macrometastases",
            "isolated tumor cells",
            "atypical ductal hyperplasia",
            "atypical lobular hyperplasia",
            "flat epithelial atypia",
            "radial scar",
            "complex sclerosing lesion",
            "intraductal papilloma",
            "papillary lesion",
            "phyllodes tumor",
            "mucinous carcinoma",
            "tubular carcinoma",
            "metaplastic carcinoma",
            "Paget disease of the nipple",
            "lymphovascular invasion",
            "extranodal extension",
            "surgical margin",
            "positive margin",
            "negative margin",
            "close margin",
        ],
    },
    "receptor_and_biomarker_status": {
        "category": "receptor_and_biomarker_status",
        "terms": [
            "ER-positive",
            "ER negative",
            "ER-negative",
            "PR-positive",
            "PR negative",
            "PR-negative",
            "HER2-positive",
            "HER2 positive",
            "HER2 negative",
            "HER2-negative",
            "HER2 equivocal",
            "ER+/PR+/HER2-",
            "ER+/PR-/HER2-",
            "ER-/PR-/HER2-",
            "ER-/PR-/HER2+",
            "ER+/PR+/HER2+",
            "ER+",
            "ER-",
            "PR+",
            "PR-",
            "HER2+",
            "HER2-",
            "HR+",
            "HR-",
            "triple negative",
            "triple-negative",
            "hormone receptor positive",
            "hormone receptor-positive",
            "hormone receptor negative",
            "hormone receptor-negative",
            "estrogen receptor positive",
            "estrogen receptor-positive",
            "estrogen receptor negative",
            "estrogen receptor-negative",
            "progesterone receptor positive",
            "progesterone receptor-positive",
            "progesterone receptor negative",
            "progesterone receptor-negative",
            "androgen receptor",
            "Ki-67 index",
            "Ki67 index",
        ],
    },
    "staging_recurrence_metastasis": {
        "category": "staging_recurrence_metastasis",
        "terms": [
            "cT1N0M0",
            "cT2N0M0",
            "cT2N1M0",
            "cT3N0M0",
            "cT3N1M0",
            "pT1N0M0",
            "pT2N0M0",
            "pT2N1M0",
            "pT3N0M0",
            "pT3N1M0",
            "T1N0M0",
            "T2N0M0",
            "T2N1M0",
            "T3N0M0",
            "T3N1M0",
            "ypT0N0",
            "ypTisN0",
            "ypT1N0",
            "ypT2N0",
            "stage I",
            "stage II",
            "stage III",
            "stage IV",
            "stage 1",
            "stage 2",
            "stage 3",
            "stage 4",
            "micrometastatic disease",
            "osseous metastasis",
            "osseous metastases",
            "bone metastasis",
            "bone metastases",
            "metastasis",
            "metastatic disease",
            "distant metastatic disease",
            "no distant metastatic disease",
            "recurrence",
            "recurrent disease",
            "local recurrence",
            "locoregional recurrence",
            "regional nodal recurrence",
            "distant metastasis",
            "metastatic recurrence",
            "nodal recurrence",
            "bone island",
            "sclerotic focus",
        ],
    },
    "systemic_endocrine_therapy": {
        "category": "systemic_endocrine_therapy",
        "terms": [
            "aromatase inhibitor",
            "aromatase inhibitor therapy",
            "endocrine therapy",
            "ongoing endocrine therapy",
            "letrozole",
            "letrozole 2.5 mg daily",
            "letrozole-associated arthralgia",
            "anastrozole",
            "exemestane",
            "tamoxifen",
            "tamoxifen therapy",
            "morning joint stiffness",
            "hot flashes",
            "calcium and vitamin D supplementation",
            "vitamin D supplementation",
            "DEXA scan",
            "bone density",
        ],
    },
    "radiology_imaging": {
        "category": "radiology_imaging",
        "terms": [
            "radiology",
            "imaging",
            "ultrasound",
            "breast ultrasound",
            "targeted breast ultrasound",
            "targeted left breast ultrasound",
            "targeted right breast ultrasound",
            "supplemental screening ultrasound",
            "screening ultrasound",
            "sonographic",
            "sonographic finding",
            "sonographic findings",
            "MRI breast",
            "breast MRI",
            "MRI pelvis",
            "bone scan",
            "CT chest",
            "CT abdomen",
            "CT pelvis",
            "CT chest/abdomen/pelvis",
            "computed tomography chest",
            "magnetic resonance imaging",
            "magnetic resonance imaging breast",
            "computed tomography",
            "scintigraphic evidence",
            "no scintigraphic evidence",
            "imaging findings",
            "surveillance imaging",
        ],
    },
    "remission_disease_status": {
        "category": "remission_disease_status",
        "terms": [
            "remission",
            "clinical remission",
            "radiographic remission",
            "clinical and radiographic remission",
            "complete remission",
            "partial remission",
            "complete response",
            "partial response",
            "stable response",
            "progressive disease",
            "disease progression",
            "no evidence of disease",
            "no evidence of recurrence",
            "no evidence of local recurrence",
            "no evidence of metastatic disease",
            "no evidence of distant metastatic disease",
            "no evidence of osseous metastasis",
            "no evidence of osseous metastases",
            "stable disease",
            "benign surveillance imaging",
        ],
    },
    "treatment_surgery_radiation": {
        "category": "treatment_surgery_radiation",
        "terms": [
            "lumpectomy",
            "left lumpectomy",
            "right lumpectomy",
            "breast-conserving surgery",
            "mastectomy",
            "partial mastectomy",
            "total mastectomy",
            "axillary dissection",
            "sentinel lymph node dissection",
            "wire-localized excision",
            "wire localized excision",
            "seed-localized excision",
            "seed localized excision",
            "re-excision",
            "margin re-excision",
            "adjuvant radiation",
            "radiation therapy",
            "regional nodes",
            "left breast and regional nodes",
            "dose-dense AC-T",
            "AC-T chemotherapy",
            "chemotherapy",
            "adjuvant chemotherapy",
            "neoadjuvant chemotherapy",
            "neoadjuvant endocrine therapy",
            "adjuvant endocrine therapy",
            "cyclophosphamide",
            "doxorubicin",
            "paclitaxel",
            "docetaxel",
            "trastuzumab",
            "pertuzumab",
            "T-DM1",
            "radiation",
        ],
    },
    "clinical_tools_scales_criteria": {
        "category": "clinical_tools_scales_criteria",
        "terms": [
            "ECOG",
            "ECOG PS",
            "ECOG performance status",
            "KPS",
            "Karnofsky Performance Status",
            "Karnofsky Performance Scale",
            "RECIST",
            "RECIST 1.1",
            "Response Evaluation Criteria in Solid Tumors",
            "iRECIST",
            "immune RECIST",
            "irRECIST",
            "PERCIST",
            "PET Response Criteria in Solid Tumors",
            "RANO",
            "RANO 2.0",
            "Response Assessment in Neuro-Oncology",
            "Macdonald criteria",
            "NANO",
            "Neurologic Assessment in Neuro-Oncology",
            "CTCAE",
            "CTCAE grade",
            "Common Terminology Criteria for Adverse Events",
            "PRO-CTCAE",
            "LI-RADS",
            "LIRADS",
            "LI-RADS 1",
            "LI-RADS 2",
            "LI-RADS 3",
            "LI-RADS 4",
            "LI-RADS 5",
            "LR-1",
            "LR-2",
            "LR-3",
            "LR-4",
            "LR-5",
            "Lung-RADS",
            "LungRADS",
            "PI-RADS",
            "PIRADS",
            "PI-RADS 1",
            "PI-RADS 2",
            "PI-RADS 3",
            "PI-RADS 4",
            "PI-RADS 5",
            "TI-RADS",
            "TIRADS",
            "ACR TI-RADS",
            "O-RADS",
            "ORADS",
            "NI-RADS",
            "NIRADS",
            "CAD-RADS",
            "CADRADS",
            "C-RADS",
            "CRADS",
            "VI-RADS",
            "VIRADS",
            "ASPECTS",
            "Alberta Stroke Program Early CT Score",
            "NIHSS",
            "NIH Stroke Scale",
            "National Institutes of Health Stroke Scale",
            "mRS",
            "modified Rankin Scale",
            "MoCA",
            "Montreal Cognitive Assessment",
            "MMSE",
            "Mini-Mental State Examination",
            "CDR",
            "Clinical Dementia Rating",
            "NIA-AA",
            "NIA-AA criteria",
            "National Institute on Aging and Alzheimer's Association criteria",
            "New York Heart Association",
            "NINCDS-ADRDA",
            "EDSS",
            "Expanded Disability Status Scale",
            "UPDRS",
            "Unified Parkinson's Disease Rating Scale",
            "JOA",
            "JOA score",
            "Japanese Orthopaedic Association score",
            "Japanese Orthopaedic Association scoring system",
            "mJOA",
            "modified Japanese Orthopaedic Association score",
            "Nurick scale",
            "Neck Disability Index",
            "Oswestry Disability Index",
            "Chelsea Critical Care Physical Assessment Tool",
            "CPAx",
            "ICU Mobility Scale",
            "Medical Research Council sum score",
            "MRC sum score",
            "Functional Independence Measure",
            "AM-PAC",
            "Activity Measure for Post-Acute Care",
            "6MWT",
            "six-minute walk test",
            "6-minute walk test",
            "Timed Up and Go",
            "Berg Balance Scale",
            "Morse Fall Scale",
            "Braden Scale",
            "Richmond Agitation-Sedation Scale",
            "RASS",
            "CAM-ICU",
            "Confusion Assessment Method for the ICU",
            "APACHE II",
            "SOFA",
            "Sequential Organ Failure Assessment",
            "qSOFA",
            "NEWS2",
            "National Early Warning Score",
            "Clinical Frailty Scale",
            "Palliative Performance Scale",
            "Edmonton Symptom Assessment System",
            "ESAS",
            "Oldenburg Sentence Test",
            "EORTC QLQ-C30",
            "FACT-G",
            "FACT-B",
            "PROMIS Global Health",
            "EQ-5D",
            "SF-36",
            "SF-12",
            "HADS",
            "Hospital Anxiety and Depression Scale",
            "HAM-D",
            "Hamilton Anxiety Scale",
            "Hamilton Depression Scale",
            "Hamilton Depression Rating Scale",
            "Hamilton Rating Scale for Depression",
            "PHQ-9",
            "GAD-7",
        ],
        "component_terms": [
            {
                "component": "Chelsea",
                "within_phrase": "Chelsea Critical Care Physical Assessment Tool",
            },
            {"component": "Macdonald", "within_phrase": "Macdonald criteria"},
            {"component": "Rankin", "within_phrase": "modified Rankin Scale"},
            {"component": "Karnofsky", "within_phrase": "Karnofsky Performance Status"},
            {"component": "Montreal", "within_phrase": "Montreal Cognitive Assessment"},
            {"component": "New York", "within_phrase": "New York Heart Association"},
            {"component": "York", "within_phrase": "New York Heart Association"},
            {"component": "Japanese", "within_phrase": "Japanese Orthopaedic Association score"},
            {"component": "Nurick", "within_phrase": "Nurick scale"},
            {"component": "Oswestry", "within_phrase": "Oswestry Disability Index"},
            {"component": "Morse", "within_phrase": "Morse Fall Scale"},
            {"component": "Braden", "within_phrase": "Braden Scale"},
            {"component": "Oldenburg", "within_phrase": "Oldenburg Sentence Test"},
            {
                "component": "Richmond",
                "within_phrase": "Richmond Agitation-Sedation Scale",
            },
            {"component": "Edmonton", "within_phrase": "Edmonton Symptom Assessment System"},
            {"component": "Hamilton", "within_phrase": "Hamilton Anxiety Scale"},
            {"component": "Hamilton", "within_phrase": "Hamilton Depression Scale"},
            {"component": "Hamilton", "within_phrase": "Hamilton Depression Rating Scale"},
            {"component": "Hamilton", "within_phrase": "Hamilton Rating Scale for Depression"},
        ],
    },
    "clinical_oncology_pathology_scales": {
        "category": "clinical_oncology_pathology_scales",
        "terms": [
            "AJCC",
            "AJCC stage",
            "AJCC staging",
            "TNM",
            "TNM staging",
            "Nottingham score",
            "Nottingham grade",
            "Nottingham Histologic Score",
            "Nottingham combined histologic grade",
            "Nottingham Prognostic Index",
            "Bloom-Richardson",
            "Bloom Richardson",
            "Scarff-Bloom-Richardson",
            "Scarff Bloom Richardson",
            "SBR",
            "SBR grade",
            "Elston-Ellis modification",
            "Oncotype DX",
            "Oncotype DX Recurrence Score",
            "MammaPrint",
            "Prosigna",
            "PAM50",
            "EndoPredict",
            "Breast Cancer Index",
            "Allred score",
            "H-score",
            "Residual Cancer Burden",
            "RCB",
            "RCB score",
            "Gleason score",
            "Gleason grade",
            "Gleason grading system",
            "ISUP grade group",
            "Bethesda system",
            "Bethesda category",
            "Bethesda System for Reporting Thyroid Cytopathology",
            "Weiss score",
            "Weiss criteria",
            "Wieneke index",
            "Wieneke index score",
            "Wieneke criteria",
            "Fuhrman grade",
            "WHO/ISUP grade",
            "Lugano classification",
            "Lugano criteria",
            "Deauville score",
            "Deauville criteria",
            "Deauville five-point scale",
        ],
        "component_terms": [
            {"component": "Nottingham", "within_phrase": "Nottingham Histologic Score"},
            {"component": "Bloom", "within_phrase": "Bloom-Richardson"},
            {"component": "Richardson", "within_phrase": "Bloom-Richardson"},
            {"component": "Scarff", "within_phrase": "Scarff-Bloom-Richardson"},
            {"component": "Elston", "within_phrase": "Elston-Ellis modification"},
            {"component": "Ellis", "within_phrase": "Elston-Ellis modification"},
            {"component": "Oncotype", "within_phrase": "Oncotype DX Recurrence Score"},
            {"component": "Gleason", "within_phrase": "Gleason score"},
            {"component": "Bethesda", "within_phrase": "Bethesda system"},
            {"component": "Weiss", "within_phrase": "Weiss criteria"},
            {"component": "Wieneke", "within_phrase": "Wieneke index score"},
            {"component": "Wieneke", "within_phrase": "Wieneke criteria"},
            {"component": "Fuhrman", "within_phrase": "Fuhrman grade"},
            {"component": "Lugano", "within_phrase": "Lugano classification"},
            {"component": "Deauville", "within_phrase": "Deauville score"},
        ],
    },
    "clinical_radiology_classification_scales": {
        "category": "clinical_radiology_classification_scales",
        "terms": [
            "Fazekas scale",
            "Fazekas grade",
            "Fazekas score",
            "medial temporal atrophy score",
            "Scheltens scale",
            "Koedam score",
            "Koedam scale",
            "global cortical atrophy scale",
            "Bosniak classification",
            "Bosniak category",
            "Bosniak v2019",
            "Fleischner criteria",
            "Fleischner Society criteria",
            "Pfirrmann grade",
            "Pfirrmann classification",
            "Modic changes",
            "Kellgren-Lawrence grade",
            "Outerbridge classification",
            "Schatzker classification",
            "Salter-Harris classification",
            "Rockwood classification",
            "Lauge-Hansen classification",
            "AO/OTA classification",
            "AOSpine classification",
            "Spinal Instability Neoplastic Score",
            "Bilsky grade",
            "epidural spinal cord compression scale",
            "Paddick conformity index",
            "Paddick gradient index",
            "Paddick index",
            "Gradient Index",
            "Conformity Index",
            "Homogeneity Index",
            "RTOG conformity index",
            "van't Riet conformation number",
            "planning target volume",
            "PTV",
            "gross tumor volume",
            "GTV",
            "clinical target volume",
            "CTV",
            "organs at risk",
            "OAR",
            "dose-volume histogram",
            "DVH",
            "V20",
            "V30",
            "D95",
            "D98",
            "D2cc",
        ],
        "component_terms": [
            {"component": "Fazekas", "within_phrase": "Fazekas grade"},
            {"component": "Fazekas", "within_phrase": "Fazekas scale"},
            {"component": "Fazekas", "within_phrase": "Fazekas score"},
            {"component": "Bosniak", "within_phrase": "Bosniak classification"},
            {"component": "Scheltens", "within_phrase": "Scheltens scale"},
            {"component": "Koedam", "within_phrase": "Koedam score"},
            {"component": "Fleischner", "within_phrase": "Fleischner Society criteria"},
            {"component": "Pfirrmann", "within_phrase": "Pfirrmann classification"},
            {"component": "Modic", "within_phrase": "Modic changes"},
            {"component": "Kellgren", "within_phrase": "Kellgren-Lawrence grade"},
            {"component": "Lawrence", "within_phrase": "Kellgren-Lawrence grade"},
            {"component": "Outerbridge", "within_phrase": "Outerbridge classification"},
            {"component": "Schatzker", "within_phrase": "Schatzker classification"},
            {"component": "Salter", "within_phrase": "Salter-Harris classification"},
            {"component": "Harris", "within_phrase": "Salter-Harris classification"},
            {"component": "Rockwood", "within_phrase": "Rockwood classification"},
            {"component": "Lauge", "within_phrase": "Lauge-Hansen classification"},
            {"component": "Hansen", "within_phrase": "Lauge-Hansen classification"},
            {"component": "Bilsky", "within_phrase": "Bilsky grade"},
            {"component": "Paddick", "within_phrase": "Paddick conformity index"},
            {"component": "Paddick", "within_phrase": "Paddick gradient index"},
            {"component": "Paddick", "within_phrase": "Paddick index"},
            {"component": "Riet", "within_phrase": "van't Riet conformation number"},
        ],
    },
    "clinical_behavioral_assessment_scales": {
        "category": "clinical_behavioral_assessment_scales",
        "terms": [
            "Self Administered Psychiatric Scales for Children and Adolescents",
            "SAFA-A",
            "SAFA-D",
            "SAFA-S",
        ],
        "component_terms": [
            {"component": "SAFA", "within_phrase": "SAFA-A"},
            {"component": "SAFA", "within_phrase": "SAFA-D"},
            {"component": "SAFA", "within_phrase": "SAFA-S"},
        ],
    },
    "clinical_genomics_molecular_pathology": {
        "category": "clinical_genomics_molecular_pathology",
        "terms": [
            "MLH1",
            "MSH2",
            "MSH6",
            "PMS2",
            "EPCAM",
            "MMR",
            "mismatch repair",
            "mismatch repair protein",
            "mismatch repair gene",
            "microsatellite instability",
            "MSI",
            "MSI-H",
            "MSS",
            "BRAF",
            "KRAS",
            "NRAS",
            "EGFR",
            "ALK",
            "ROS1",
            "RET",
            "MET",
            "NTRK",
            "BRCA1",
            "BRCA2",
            "PALB2",
            "PIK3CA",
            "TP53",
            "PTEN",
            "ERBB2",
            "PD-L1",
            "PDL1",
            "Ki-67",
            "Ki67",
            "IHC",
            "immunohistochemistry",
            "FISH",
            "PCR",
            "NGS",
            "next generation sequencing",
            "whole exome sequencing",
            "WES",
            "whole genome sequencing",
            "WGS",
            "RNA sequencing",
            "RNA-seq",
        ],
    },
    "general_clinical_terms": {
        "category": "general_clinical_terms",
        "terms": [
            "myasthenia gravis",
            "acute motor axonal neuropathy",
            "Guillain-Barré syndrome",
            "Guillain-Barre syndrome",
            "de novo",
            "de-escalation",
            "de-adaptation",
            "et al.",
            "et al",
            "Corman et al.",
            "Corman et al",
            "in situ",
            "in vitro",
            "in vivo",
            "ex vivo",
            "in silico",
            "ex situ",
            "in utero",
            "in planta",
            "in ovo",
            "in cellulo",
            "in chemico",
            "ab initio",
            "post hoc",
            "per se",
            "vice versa",
            "status post",
            "veno-venous extracorporeal membrane oxygenation",
            "veno-venous ECMO",
            "veno-venous",
            "venovenous ECMO",
            "VV ECMO",
            "veno-arterial extracorporeal membrane oxygenation",
            "veno-arterial ECMO",
            "veno-arterial",
            "VA ECMO",
            "extracorporeal membrane oxygenation",
            "ECMO",
            "arteriovenous fistula",
            "arterio-venous fistula",
            "arteriovenous malformation",
            "hemicraniectomy",
            "hemicolectomy",
            "hemiparesis",
            "hemiplegia",
            "hemi-abdomen",
            "hemisensory loss",
            "Heiner syndrome",
            "dermatomyositis",
            "dermatomal distribution",
            "dermatologic toxicity",
            "dermo-hypodermal",
            "dermopathy",
            "Replogle tube",
            "Vo thalamotomy",
            "Vo nucleus",
            "Jackson Pratt drain",
            "Bruner incisions",
            "Pfannenstiel incision",
            "Langhans giant cells",
            "McFarland standard",
            "P. insidiosum",
            "Endo-GIA",
            "Sof-lex/3 M ESPE",
            "subaortic membrane",
            "Merkel cell carcinoma",
            "Merkel cell cancer",
            "factor XIII",
            "von Hippel-Lindau disease",
            "von Hippel-Lindau syndrome",
            "von Willebrand disease",
            "von Willebrand factor",
            "von Willebrand factor antigen",
            "Wiskott-Aldrich syndrome",
            "Li-Fraumeni syndrome",
            "Peutz-Jeghers syndrome",
            "Lynch syndrome",
            "Cowden syndrome",
        ],
        "component_terms": [
            {"component": "de", "within_phrase": "de novo"},
            {"component": "de", "within_phrase": "de-escalation"},
            {"component": "escalation", "within_phrase": "de-escalation"},
            {"component": "de", "within_phrase": "de-adaptation"},
            {"component": "adaptation", "within_phrase": "de-adaptation"},
            {"component": "gravis", "within_phrase": "myasthenia gravis"},
            {"component": "novo", "within_phrase": "de novo"},
            {"component": "et", "within_phrase": "et al."},
            {"component": "al", "within_phrase": "et al."},
            {"component": "et", "within_phrase": "et al"},
            {"component": "al", "within_phrase": "et al"},
            {"component": "Corman", "within_phrase": "Corman et al."},
            {"component": "Corman", "within_phrase": "Corman et al"},
            {"component": "situ", "within_phrase": "in situ"},
            {"component": "vitro", "within_phrase": "in vitro"},
            {"component": "vivo", "within_phrase": "in vivo"},
            {"component": "vivo", "within_phrase": "ex vivo"},
            {"component": "ex", "within_phrase": "ex vivo"},
            {"component": "ex", "within_phrase": "ex situ"},
            {"component": "silico", "within_phrase": "in silico"},
            {"component": "utero", "within_phrase": "in utero"},
            {"component": "planta", "within_phrase": "in planta"},
            {"component": "ovo", "within_phrase": "in ovo"},
            {"component": "cellulo", "within_phrase": "in cellulo"},
            {"component": "chemico", "within_phrase": "in chemico"},
            {"component": "initio", "within_phrase": "ab initio"},
            {"component": "hoc", "within_phrase": "post hoc"},
            {"component": "se", "within_phrase": "per se"},
            {"component": "versa", "within_phrase": "vice versa"},
            {"component": "veno", "within_phrase": "veno-venous extracorporeal membrane oxygenation"},
            {"component": "veno", "within_phrase": "veno-venous ECMO"},
            {"component": "veno", "within_phrase": "veno-venous"},
            {"component": "veno", "within_phrase": "veno-arterial extracorporeal membrane oxygenation"},
            {"component": "veno", "within_phrase": "veno-arterial ECMO"},
            {"component": "veno", "within_phrase": "veno-arterial"},
            {"component": "hemi", "within_phrase": "hemi-abdomen"},
            {"component": "Heiner", "within_phrase": "Heiner syndrome"},
            {"component": "dermo", "within_phrase": "dermo-hypodermal"},
            {"component": "Replogle", "within_phrase": "Replogle tube"},
            {"component": "Vo", "within_phrase": "Vo thalamotomy"},
            {"component": "Vo", "within_phrase": "Vo nucleus"},
            {"component": "Jackson", "within_phrase": "Jackson Pratt drain"},
            {"component": "Pratt", "within_phrase": "Jackson Pratt drain"},
            {"component": "Bruner", "within_phrase": "Bruner incisions"},
            {"component": "Pfannenstiel", "within_phrase": "Pfannenstiel incision"},
            {"component": "Langhans", "within_phrase": "Langhans giant cells"},
            {"component": "McFarland", "within_phrase": "McFarland standard"},
            {"component": "P.", "within_phrase": "P. insidiosum"},
            {"component": "GIA", "within_phrase": "Endo-GIA"},
            {"component": "M", "within_phrase": "Sof-lex/3 M ESPE"},
            {"component": "Sof-lex", "within_phrase": "Sof-lex/3 M ESPE"},
            {"component": "Merkel", "within_phrase": "Merkel cell carcinoma"},
            {"component": "XIII", "within_phrase": "factor XIII"},
            {"component": "von", "within_phrase": "von Hippel-Lindau disease"},
            {"component": "von", "within_phrase": "von Willebrand disease"},
            {"component": "von", "within_phrase": "von Willebrand factor"},
            {"component": "von", "within_phrase": "von Willebrand factor antigen"},
            {"component": "Hippel", "within_phrase": "von Hippel-Lindau disease"},
            {"component": "Lindau", "within_phrase": "von Hippel-Lindau disease"},
            {"component": "Willebrand", "within_phrase": "von Willebrand disease"},
            {"component": "Willebrand", "within_phrase": "von Willebrand factor"},
            {"component": "Willebrand", "within_phrase": "von Willebrand factor antigen"},
            {"component": "Wiskott", "within_phrase": "Wiskott-Aldrich syndrome"},
            {"component": "Aldrich", "within_phrase": "Wiskott-Aldrich syndrome"},
            {"component": "Li", "within_phrase": "Li-Fraumeni syndrome"},
            {"component": "Fraumeni", "within_phrase": "Li-Fraumeni syndrome"},
            {"component": "Peutz", "within_phrase": "Peutz-Jeghers syndrome"},
            {"component": "Jeghers", "within_phrase": "Peutz-Jeghers syndrome"},
            {"component": "Lynch", "within_phrase": "Lynch syndrome"},
            {"component": "Cowden", "within_phrase": "Cowden syndrome"},
        ],
    },
}

# The built-in list is manually curated, general, and non-site-specific. It is
# a targeted semantic-preservation set.


def _build_protected_terms_profile(
    protected_clinical_terms,  # Runtime rule config or None.
    *,
    include_builtin_protected_clinical_terms: bool,  # Include curated built-in terms.
) -> dict[str, Any] | None:
    """Validate configured terms and return a normalized exact-match index.

    `protected_clinical_terms` uses the runtime shape:
    `rule_id -> {"category": str, "terms": list[str]}`.

    The returned profile contains normalized whole-span terms and rule IDs for
    metadata. It is used only as a post-pyDeid false-positive veto; it never
    creates spans or scans the full note.
    """

    combined: dict[str, dict[str, Any]] = {}
    if include_builtin_protected_clinical_terms:
        combined.update(_BUILTIN_PROTECTED_CLINICAL_TERMS)
    if protected_clinical_terms:
        if not isinstance(protected_clinical_terms, dict):
            raise ValueError("protected_clinical_terms must be a dictionary keyed by rule ID.")
        combined.update(protected_clinical_terms)

    if not combined:
        return None

    term_index: dict[str, dict[str, str]] = {}
    component_index: dict[str, list[dict[str, Any]]] = {}
    rule_ids: list[str] = []
    for rule_id, rule_config in combined.items():
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError("protected_clinical_terms contains a missing or empty rule ID.")
        sanitized_rule_id = rule_id.strip()
        if not isinstance(rule_config, dict):
            raise ValueError("protected_clinical_terms rule config must be a dictionary.")

        category = rule_config.get("category")
        if not isinstance(category, str) or not category.strip():
            raise ValueError("protected_clinical_terms rule config requires a nonempty category.")
        category = category.strip()

        terms = rule_config.get("terms", [])
        if terms is None:
            terms = []
        if not isinstance(terms, list):
            raise ValueError("protected_clinical_terms terms must be a list.")

        rule_ids.append(sanitized_rule_id)
        for term in terms:
            if not isinstance(term, str) or not term.strip():
                raise ValueError("protected_clinical_terms terms must be nonempty strings.")
            normalized = _normalize_protected_term(term)
            existing = term_index.get(normalized)
            if existing is not None and existing["rule_id"] != sanitized_rule_id:
                raise ValueError("protected_clinical_terms contains duplicate normalized terms.")
            term_index[normalized] = {
                "rule_id": sanitized_rule_id,
                "category": category,
            }

        component_terms = rule_config.get("component_terms", [])
        if component_terms is None:
            component_terms = []
        if not isinstance(component_terms, list):
            raise ValueError("protected_clinical_terms component_terms must be a list.")
        if not terms and not component_terms:
            raise ValueError(
                "protected_clinical_terms rule config requires at least one term or component."
            )
        for component_config in component_terms:
            if not isinstance(component_config, dict):
                raise ValueError("protected_clinical_terms component_terms entries must be objects.")
            component = component_config.get("component")
            within_phrase = component_config.get("within_phrase")
            if not isinstance(component, str) or not component.strip():
                raise ValueError("protected_clinical_terms component_terms require a component.")
            if not isinstance(within_phrase, str) or not within_phrase.strip():
                raise ValueError("protected_clinical_terms component_terms require a within_phrase.")
            normalized_component = _normalize_protected_term(component)
            normalized_phrase = _normalize_protected_term(within_phrase)
            if re.search(rf"(?<!\w){re.escape(normalized_component)}(?!\w)", normalized_phrase) is None:
                raise ValueError(
                    "protected_clinical_terms component must appear in its configured phrase."
                )
            component_index.setdefault(normalized_component, []).append(
                {
                    "rule_id": sanitized_rule_id,
                    "category": category,
                    "component": normalized_component,
                    "within_phrase": normalized_phrase,
                    "phrase_pattern": _compile_phrase_pattern(within_phrase),
                }
            )

    return {"terms": term_index, "component_terms": component_index, "rule_ids": rule_ids}


def _protected_term_match(
    span: PHISpan,  # pyDeid span to check for exact protected-term match.
    protected_terms_profile: dict[str, Any] | None,  # Normalized protected-term index.
    original_text: str = "",  # Full original note text for phrase-component checks.
) -> dict[str, str] | None:
    """Return protected-term provenance when a pyDeid span exactly matches."""
    if not protected_terms_profile:
        return None
    normalized_span = _normalize_protected_term(span.text)
    exact_match = protected_terms_profile["terms"].get(normalized_span)
    if exact_match is not None:
        return {
            **exact_match,
            "policy": "exact_normalized_span_match",
        }

    for component_rule in protected_terms_profile.get("component_terms", {}).get(
        normalized_span, []
    ):
        if _span_component_appears_in_phrase_context(span, original_text, component_rule):
            return {
                "rule_id": component_rule["rule_id"],
                "category": component_rule["category"],
                "policy": "exact_normalized_component_within_phrase",
                "component": component_rule["component"],
                "within_phrase": component_rule["within_phrase"],
            }

    return None


def _protected_term_metadata(
    match: dict[str, str],  # Rule/category provenance for one protected match.
) -> dict[str, str]:
    """Translate a protected-term match into span/audit metadata fields."""
    metadata = {
        "project_protected_term_policy": "exact_normalized_span_match",
        "project_protected_term_rule_id": match["rule_id"],
        "project_protected_term_category": match["category"],
    }
    policy = match.get("policy")
    if policy:
        metadata["project_protected_term_policy"] = policy
    if "component" in match:
        metadata["project_protected_component"] = match["component"]
    if "within_phrase" in match:
        metadata["project_protected_within_phrase"] = match["within_phrase"]
    return metadata


def _normalize_protected_term(
    value: str,  # Term or span text to normalize for exact match.
) -> str:
    """Normalize terms for exact whole-span matching, not substring matching."""
    text = value.strip().casefold()
    text = text.strip("([")
    text = text.rstrip(".,;:)]")
    return re.sub(r"\s+", " ", text).strip()


def _compile_phrase_pattern(
    phrase: str,  # Approved clinical phrase that may contain a risky component.
) -> Pattern[str]:
    """Compile a bounded phrase matcher for span-local component protection."""
    pieces = [re.escape(piece) for piece in phrase.strip().split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(pieces) + r"(?!\w)", re.IGNORECASE)


def _span_component_appears_in_phrase_context(
    span: PHISpan,  # pyDeid component span such as `Chelsea` or `Fazekas`.
    original_text: str,  # Full original note text.
    component_rule: dict[str, Any],  # Normalized phrase-component rule.
) -> bool:
    """Return true when a component span sits inside its approved phrase.

    This remains span-local: the search window is bounded around the pyDeid
    span, and the rule never creates new spans or scans the whole note.
    """
    if not original_text:
        return False
    phrase_length = len(component_rule["within_phrase"])
    window_start = max(0, span.start - phrase_length - 4)
    window_end = min(len(original_text), span.end + phrase_length + 4)
    window = original_text[window_start:window_end]

    pattern = component_rule["phrase_pattern"]
    for match in pattern.finditer(window):
        absolute_start = window_start + match.start()
        absolute_end = window_start + match.end()
        if absolute_start <= span.start and span.end <= absolute_end:
            return True
    return False
