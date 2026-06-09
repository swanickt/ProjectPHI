"""Project-stable replacement reconstruction from original-note offsets.

Reconstruction is used when ProjectPHI needs final replacements that may differ
from pyDeid's initial surrogate text, such as stable date shifts, stable name
aliases, or protected clinical-term preservation.

This module rebuilds the final note from the original note plus normalized
`PHISpan` offsets. It does not edit pyDeid's already-de-identified output string,
because project replacements may have different lengths and can invalidate
pyDeid-output offsets.

Offset convention:
- `PHISpan.start` / `PHISpan.end` remain offsets in the original note.
- `pydeid_surrogate_start` / `pydeid_surrogate_end`, when present, refer to
  pyDeid's initially de-identified output.
- `project_replacement_start` / `project_replacement_end` are added here and
  refer to the final ProjectPHI output text.

Replacement priority:
1. Preserve protected clinical terms when a pyDeid span exactly matches one, or
   when a configured risky component appears inside an approved clinical phrase.
2. Preserve narrow clinical abbreviation false positives such as `PMHx`.
3. Preserve strict obstetric-history shorthand such as `G1P0A0`.
4. Apply stable date shifting/preservation/fallback when date shifting is enabled.
5. Apply stable patient-name aliases when patient alias replacement is enabled.
6. Apply stable provider-name aliases when provider alias replacement is enabled,
   including narrow adjacent action-word rescue after explicit provider aliases.
7. Preserve narrow ordinary-token false positives such as articles/pronouns.
8. Preserve narrow title-token fragments such as pyDeid-split `Dr.` pieces.
9. Preserve narrow title-context action-word false positives.
10. Fall back to pyDeid's replacement, or `<PHI>` if pyDeid did not provide one.

Examples:
    Original:
        "Jane Smith had imaging on January 5, 2024."

    With patient-name identity `Alex Bennett` and date offset +10:
        "Alex Bennett had imaging on January 15, 2024."

    Original:
        "BI-RADS 2 was documented on January 2024."

    If `BI-RADS 2` is a protected term and date offset is +25:
        "BI-RADS 2 was documented on February 2024."

Safety:
- deterministic low-risk pyDeid span overlaps are pruned before reconstruction;
- unresolved mixed overlaps still fail closed with `ValueError`;
- raw original text is copied only outside detected spans;
- replacement offsets are recorded in project-final coordinates.
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Any

from .date_shift import (
    _date_shift_metadata_for_month_year_span,
    _date_shift_metadata_for_partial_month_day_span,
    _date_shift_policy_for_full_date_span,
    _is_date_like_span,
    _is_holiday_or_season_span,
    _is_parseable_month_year_span,
    _is_parseable_partial_month_day_span,
    _is_parseable_full_date_span,
    _is_score_or_fraction_date_span,
    _is_time_span,
    _is_year_only_span,
    _score_or_fraction_date_metadata,
    _shift_full_date_span,
    _shift_month_year_span,
    _shift_partial_month_day_span,
)
from .models import PHISpan
from .patient_names import _name_policy_metadata, _project_patient_name_replacement
from .provider_names import (
    _project_provider_adjacent_action_word_metadata,
    _project_provider_name_replacement,
    _provider_name_policy_metadata,
)
from .protected_terms import _protected_term_match, _protected_term_metadata
from .title_context import (
    _title_context_action_word_match,
    _title_context_action_word_metadata,
    _title_token_fragment_match,
    _title_token_fragment_metadata,
)

_ORDINARY_ARTICLE_PRONOUN_TOKENS = {
    "a",
    "an",
    "he",
    "her",
    "his",
    "she",
    "the",
}

_INITIAL_CONTEXT_PREFIXES = (
    "case",
    "control",
    "doctor",
    "family",
    "patient",
    "participant",
    "subject",
)

_TITLE_INITIAL_CONTEXT_PREFIXES = {
    "Dr.",
    "Mr.",
    "Mrs.",
    "Ms.",
}

_NH_CONTEXT_AFTER = (
    " resident",
    " patient",
    " facility",
    " placement",
    " transfer",
    " staff",
)

_NH_CONTEXT_BEFORE = (
    " from ",
    " at ",
    " in ",
    " to ",
    " transferred from ",
    " sent from ",
    " discharged to ",
)

_OBSTETRIC_HISTORY_PATTERNS = (
    re.compile(r"^G\d{1,2}\s*P\d{1,2}(?:\s*A\d{1,2})?(?:\s*L\d{1,2})?$", re.IGNORECASE),
    re.compile(r"^G\d{1,2}\s*T\d{1,2}\s*P\d{1,2}\s*A\d{1,2}\s*L\d{1,2}$", re.IGNORECASE),
    re.compile(r"^G\d{1,2}\s*P\d{4}$", re.IGNORECASE),
    re.compile(r"^G\d{1,2}\s*P\d{1,2}[-+]\d{1,2}(?:[-+]\d{1,2})?(?:[-+]\d{1,2})?$", re.IGNORECASE),
)

_PMH_CONTEXT_TERMS = (
    "past medical",
    "medical history",
    "pmh of",
    "pmh significant",
    "pmh notable",
    "with pmh",
)

_SAH_CONTEXT_TERMS = (
    "aneurysm",
    "ct head",
    "cta head",
    "external ventricular drain",
    "fisher grade",
    "haemorrhage",
    "hemorrhage",
    "hunt-hess",
    "intracranial",
    "lumbar puncture",
    "nimodipine",
    "subarachnoid",
    "thunderclap",
    "traumatic",
    "vasospasm",
)

_MSH_CONTEXT_TERMS = (
    "ihc",
    "immunohistochemical",
    "immunohistochemistry",
    "lynch",
    "mismatch repair",
    "mlh1",
    "mmr",
    "msh2",
    "msh6",
    "nuclear expression",
    "pms2",
)

_WES_CONTEXT_TERMS = (
    "exome",
    "genetic testing",
    "genome",
    "sequencing",
    "trio",
    "variant",
    "whole exome sequencing",
)

_SAM_CONTEXT_TERMS = (
    "echo",
    "echocardiogram",
    "hypertrophic cardiomyopathy",
    "left ventricular outflow tract",
    "lvot",
    "mitral",
    "systolic anterior motion",
    "subaortic membrane",
)

_AMAN_CONTEXT_TERMS = (
    "acute motor axonal neuropathy",
    "gbs",
    "guillain",
    "neuropathy",
)

_NIA_AA_CONTEXT_TERMS = (
    "alzheimer",
    "alzheimer's association",
    "national institute on aging",
    "nia-aa",
    "nia-aa criteria",
)

_GCS_COMPONENT_RE = re.compile(r"^E[1-4]V[1-5]M[1-6]$", re.IGNORECASE)
_TNM_STAGE_RE = re.compile(
    r"^(?:[cpyra]{0,3})?T(?:is|[0-4][a-d]?|X)N(?:[0-3][a-d]?|X)M(?:0|1[a-c]?|X)$",
    re.IGNORECASE,
)
_DURATION_TRAVEL_RE = re.compile(
    r"^\d+(?:\.\d+)?\s*(?:day|days|week|weeks|hour|hours)\s+"
    r"(?:drive|flight|walk|hike|trip|travel)$",
    re.IGNORECASE,
)
_GENOMIC_COORDINATE_RANGE_RE = re.compile(r"^\d{6,}-\d{7,}$")
_LONG_FLOAT_FRAGMENT_RE = re.compile(r"^\d{8,}$")

_GCS_CONTEXT_TERMS = (
    "gcs",
    "glasgow",
    "glasgow coma scale",
)

_TNM_CONTEXT_TERMS = (
    "ajcc",
    "cancer control",
    "pathologic diagnosis",
    "pathological diagnosis",
    "stage",
    "staging",
    "tnm",
    "tumor",
    "tumour",
    "union for international cancer control",
)

_GENOMIC_COORDINATE_CONTEXT_TERMS = (
    "amniocentesis",
    "arr ",
    "base pair",
    "base pairs",
    "alteration",
    "alterations",
    "breakpoint",
    "breakpoints",
    "cgh",
    "chr",
    "chromosomal",
    "chromosome",
    "copy number",
    "cytoband",
    "deletion",
    "duplication",
    "fish",
    "genomic",
    "grch",
    "hg19",
    "hg38",
    "karyotype",
    "microarray",
    "q22",
    "q25",
)

_LONG_FLOAT_MEASUREMENT_CONTEXT_TERMS = (
    "cm",
    "diameter",
    "dimension",
    "dimensions",
    "greatest dimension",
    "length",
    "lesion",
    "mass",
    "measurement",
    "mm",
    "size",
    "thickness",
    "tumor size",
    "tumour size",
    "width",
)

_CLINICAL_CODE_CONTEXT_RULES = {
    "STEC": ("infectious_disease_abbreviation", ("e. coli", "shiga", "stool", "toxin")),
    "WM": ("hematology_abbreviation", ("igm", "myd88", "waldenstrom", "macroglobulinemia")),
    "EBER": ("pathology_marker", ("ebv", "ish", "in situ hybridization", "immunohistochemical", "neoplastic", "pathology")),
    "BEV": ("oncology_drug_abbreviation", ("bevacizumab", "carboplatin", "pemetrexed", "chemotherapy", "maintenance")),
    "DES": ("pathology_marker", ("desmin", "gene variant", "myopathy", "rabbit pab", "immunohistochemical", "stain")),
    "TPC": ("pathology_touch_prep_abbreviation", ("touch prep", "touch preparation", "intraoperative", "frozen section", "diagnosis called")),
    "TPD": ("pathology_touch_prep_abbreviation", ("touch prep", "touch preparation", "intraoperative", "frozen section", "diagnosis called")),
    "TPE": ("pathology_touch_prep_abbreviation", ("touch prep", "touch preparation", "intraoperative", "frozen section", "diagnosis called")),
    "TPF": ("pathology_touch_prep_abbreviation", ("touch prep", "touch preparation", "intraoperative", "frozen section", "diagnosis called")),
    "HAMN": ("pathology_abbreviation", ("appendiceal", "lamn", "mucinous", "neoplasm")),
    "GNAS": ("gene_symbol", ("gene", "mutation", "variant", "snapshot", "molecular")),
    "ROIS": ("imaging_measurement_abbreviation", ("axial", "image", "lesion", "region", "roi")),
    "PH": ("clinical_abbreviation", ("pulmonary hypertension", "halt", "mdct", "valve")),
    "JC": ("virus_abbreviation", ("virus", "pcr", "csf", "positive", "negative")),
    "KEGG": ("bioinformatics_resource", ("pathway", "enrichment", "ras", "mapk", "pi3k")),
    "XY": ("karyotype_notation", ("karyotype", "chromosome", "chromosomal", "amniocentesis", "cnv")),
    "DEL": ("karyotype_notation", ("karyotype", "chromosome", "chromosomal", "amniocentesis", "cnv")),
    "IMM": ("pathology_report_abbreviation", ("imm recut", "h&e imm", "imm x", "neg cont", "neg-her2", "her2", "er-c", "pr-c", "special stain", "immunohistochemical")),
    "AXT": ("pathology_report_abbreviation", ("axillary tail", "breast", "block", "site")),
    "KER": ("pathology_report_abbreviation", ("cytokeratin cocktail", "cytokeratin", "keratin", "2/neu", "her2", "her-2", "c-erb", "membrane staining", "score 3")),
    "MAK": ("pathology_marker", ("mak-6", "ema", "desmin", "myogenin", "actin")),
    "LYM": ("lab_abbreviation", ("lym%", "lymphocyte", "lymphocytes", "lymph")),
    "HEE": ("pathology_stain_abbreviation", ("hee-stained", "stained sections", "stains for cytokeratins", "cytokeratins", "h&e")),
    "FS": ("pathology_report_abbreviation", ("frozen section", "intraoperative", "fs:", "fs.", "fs ")),
    "FSA": ("pathology_report_abbreviation", ("frozen section", "intraoperative", "diagnosis called")),
    "FSB": ("pathology_report_abbreviation", ("frozen section", "intraoperative", "diagnosis called")),
    "FSC": ("pathology_report_abbreviation", ("frozen section", "intraoperative", "diagnosis called")),
    "FSD": ("pathology_report_abbreviation", ("frozen section", "intraoperative", "diagnosis called")),
    "GIA": ("procedure_device_abbreviation", ("gia-75", "gastrointestinal anastomosis", "stapler", "linear stapler", "endo-gia")),
    "MIR": ("molecular_biology_abbreviation", ("microrna", "mirna", "mir gene", "gene mir", "mir4737")),
    "LUM": ("pathology_block_map_abbreviation", ("left ureter margin", "ureter margin", "r um", "rum", "ureteric orifice")),
    "BROCK": ("procedure_eponym_fragment", ("brockenbrough", "transseptal", "needle")),
    "VO": ("neuroanatomy_abbreviation", ("ventral intermediate", "vim", "nuclei", "thalamotomy")),
    "IOPA": ("dental_radiograph_abbreviation", ("radiograph", "radiographic", "intra-oral", "periapical")),
    "CUN": ("acupuncture_measurement", ("acupuncture", "acupoint", "depth", "inserted", "needle", "needles")),
    "ASMA": ("autoantibody_abbreviation", ("anti-smooth muscle", "smooth muscle antibody", "autoimmune", "auto-immune", "antibody", "stain", "stains", "desmin")),
    "FUHRMAN": ("pathology_grade_eponym", ("grade", "nuclear", "renal", "rcc", "carcinoma", "pathology")),
    "ALLRED": ("pathology_score_eponym", ("score", "scoring", "proportion", "intensity", "er", "estrogen", "receptor")),
    "LAUREN": ("pathology_classification_eponym", ("intestinal type", "diffuse type", "gastric", "histologic type", "classification", "typus intestinalis", "mixed type", "acc. to lauren", "lauren class")),
    "HEMI": ("clinical_prefix_fragment", ("hemicraniectomy", "hemicolectomy", "hemi-colectomy", "hemiparesis", "hemiplegia", "hemihepatectomy", "hemi-hepatectomy", "hemi hepatectomy", "hemilaminectomy", "hemi-laminectomy", "hemithyroidectomy", "hemi-thyroidectomy", "hemimaxillectomy", "hemi-maxillectomy", "hemi-scrotum", "hemi-pelvis", "hemi-vertebrae", "hemi-cord", "hemisensory", "hemi-epifysiodesis", "hemi-thorax", "hemithorax", "hemi-trigone", "hemi-crvo", "hemifacial", "hemi-abdominal", "hemi vagina", "hemi-space", "hemi-liver")),
    "HERTEL": ("ophthalmic_measurement_eponym", ("exophthalmometry", "proptosis", "globe", "visual acuity", "left 26 mm", "right 16 mm")),
    "COLL": ("pathology_report_template_fragment", ("date coll", "coll. time", "time in formalin", "collected", "collection", "specimen")),
    "GROU": ("pathology_report_template_fragment", ("provider group", "reporting group", "group")),
}

_ORDINARY_CLINICAL_PROSE_TERMS = {
    "blood": ("blood_pressure_or_lab_prose", ("pressure", "cultures", "culture", "count", "smear", "gas", "glucose", "cell", "chemistry")),
    "vital": ("vital_signs_prose", ("sign", "signs", "normal", "stable")),
    "computed": ("computed_tomography_prose", ("tomography", "ct", "revealed", "showed")),
    "tomography": ("computed_tomography_prose", ("computed", "ct", "revealed", "showed")),
    "cultures": ("culture_prose", ("blood", "urine", "wound", "grew", "negative", "positive")),
    "culture": ("culture_prose", ("blood", "urine", "wound", "grew", "negative", "positive")),
    "topical": ("treatment_prose", ("antibiotic", "antibiotics", "steroid", "steroids", "therapy")),
    "follow-up": ("follow_up_prose", ("visit", "after", "appointment", "months", "weeks", "scheduled", "examination", "care")),
    "well-child": ("well_child_prose", ("examination", "visit", "clinic")),
    "left-sided": ("laterality_prose", ("pain", "weakness", "lesion", "procedure", "surgery", "abdominal", "discomfort")),
    "low-risk": ("risk_status_prose", ("disease", "mds", "tumor", "tumour", "patient")),
    "low-income": ("social_context_prose", ("clinic", "resident", "residents", "housing", "support", "assistance")),
    "pre-employment": ("exam_context_prose", ("examination", "exam")),
    "clamped": ("procedure_prose", ("tube", "drain", "catheter")),
    "clamping": ("procedure_prose", ("tube", "drain", "catheter")),
    "general": ("clinical_role_prose", ("practitioner", "practitioners", "practice")),
    "practitioners": ("clinical_role_prose", ("general", "home care", "doctors")),
    "homecare": ("care_context_prose", ("staff", "agency", "help", "medications", "mother", "support")),
    "findings": ("imaging_findings_prose", ("imaging", "mr", "mri", "ct", "presentation")),
    "with": ("treatment_prose", ("topical antibiotics", "treated", "private practitioner")),
    "and": ("cardiology_or_abbreviation_prose", ("mr and ph", "halt and rlm", "mdct")),
    "prior": ("temporal_prose", ("prior to", "accident", "surgery", "surgeries")),
    "december": ("month_reference_prose", ("physician in", "episodic", "shortness", "winter")),
    "gross": ("pathology_report_header_prose", ("description", "specimen", "pathology", "diagnosis", "section")),
    "diagnosis": ("pathology_report_header_prose", ("dr. diagnosis", "final", "pathologic", "pathology", "clinical", "pre-op", "post-op", "addendum", "revised", "permanent")),
    "pathology": ("pathology_report_header_prose", ("pathology report", "pathology service", "report", "surgical", "department", "final", "diagnosis")),
    "clinical": ("pathology_report_header_prose", ("clinical history", "clinical data", "clinical information")),
    "history": ("pathology_report_header_prose", ("clinical history", "history:", "medical history")),
    "microscopic": ("pathology_report_header_prose", ("microscopic/diagnostic", "microscopic description", "microscopic diagnosis", "microscopic examination", "microscopic vascular invasion", "vascular invasion identified")),
    "surgical": ("pathology_report_header_prose", ("surgical pathol", "surgical pathology", "surgical margins", "surgical specimen")),
    "addendum": ("pathology_report_header_prose", ("addendum:", "addendum report", "start of addendum", "date complete", "oncotype dx")),
    "comment": ("pathology_report_header_prose", ("comment:", "see comment", "diagnosis", "pathology report")),
    "specimen": ("pathology_report_header_prose", ("specimen received", "specimen is received", "specimen size", "specimen weight", "specimen type", "received fresh", "labeled", "labelled")),
    "margins": ("pathology_report_header_prose", ("surgical margins", "resection margins", "margins involved", "margins uninvolved")),
    "margin": ("pathology_report_header_prose", ("surgical margin", "resection margin", "deep margin", "margin negative", "margin positive", "margin involved", "margin uninvolved")),
    "final": ("pathology_report_header_prose", ("final diagnosis", "final pathologic", "final review")),
    "tumor": ("pathology_report_header_prose", ("tumor size", "tumor type", "tumor site", "tumor grade", "tumor obtained", "cancer genomics study", "obtained for genomics")),
    "paraffin": ("pathology_report_header_prose", ("paraffin block", "paraffin embedded", "ffpe", "mgmt", "molecular", "assay", "pathology")),
    "consultation": ("pathology_report_header_prose", ("intraoperative", "frozen", "section", "pathology")),
    "intraoperative": ("pathology_report_header_prose", ("consultation", "frozen", "section", "pathology")),
    "record": ("medical_record_prose", ("medical record", "record review", "record no", "record number", "physician of record")),
    "record.": ("medical_record_prose", ("medical record", "record review", "record no", "record number", "physician of record")),
    "score": ("clinical_score_prose", ("mrs score", "nihss score", "ecog score", "karnofsky score", "bi-rads score", "allred score", "nottingham score")),
}

_VENDOR_REFERENCE_CONTEXT_RULES = {
    "VARIAN": ("vendor_reference_metadata", ("truebeam", "hyperarc", "linac", "medical systems", "810-ms", "icp-ms")),
    "SRL": ("vendor_reference_metadata", ("clonit", "assay", "variant catcher", "pcr")),
    "CARIS": ("vendor_reference_metadata", ("life science", "laboratory", "sequencing")),
    "PROMEGA": ("vendor_reference_metadata", ("powerplex", "kit", "multiplex")),
    "OTSUKA": ("vendor_reference_metadata", ("pharmaceutical", "ophthalmic", "mucosta")),
    "SENKO": ("vendor_reference_metadata", ("medical", "instrument", "mera")),
    "BRUKER": ("vendor_reference_metadata", ("maldi", "tof", "database", "spectrum")),
    "DAKO": ("vendor_reference_metadata", ("clone", "antibody", "immunohistochemical")),
    "VITEK": ("vendor_reference_metadata", ("maldi", "tof", "blood cultures", "spectrometry", "system", "isolates", "biomérieux", "biomerieux")),
    "ELLA": ("vendor_reference_metadata", ("prosthesis", "ella-cs", "esophageal")),
    "ESPE": ("vendor_reference_metadata", ("3m", "3 m", "dental", "restoration")),
    "WEBSTER": (
        "vendor_reference_metadata",
        ("biosense", "carto", "thermocool"),
    ),
    "JOHNSON": (
        "vendor_reference_metadata",
        ("johnson & johnson", "& johnson", "biosense webster", "ethicon", "prolene"),
    ),
    "RAMSEY": ("vendor_reference_metadata", ("petmap",)),
    "INGELHEIM": ("vendor_reference_metadata", ("boehringer", "vetmedin", "pimobendan")),
    "AMRHEIN": ("vendor_reference_metadata", ("boehringer", "ingelheim", "vetmedin")),
    "ZAMBON": ("vendor_reference_metadata", ("flagyl", "metronidazole", "antibiotic")),
    "STRECK": ("vendor_reference_metadata", ("dna bct", "cfdna", "blood collected", "tube")),
    "AGILENT": ("vendor_reference_metadata", ("bioanalyzer", "dna chips", "cfdna", "sequencing")),
    "SOFIA": ("vendor_reference_metadata", ("catheter", "microvention", "terumo", "intracranial")),
    "SMITH": ("vendor_reference_metadata", ("smith & nephew", "smith and nephew", "renasys", "pico")),
    "SAPIEN": ("vendor_reference_metadata", ("edwards", "valve", "tavr")),
    "MERA": ("vendor_reference_metadata", ("sacuum", "suction", "senko", "drainage")),
    "KERR": ("vendor_reference_metadata", ("herculite", "premise", "dental", "composite", "restoration")),
    "KULZER": ("vendor_reference_metadata", ("tool kit", "polishing", "restoration", "dental")),
    "ZEISS": ("vendor_reference_metadata", ("carl zeiss", "axioplan", "cirrus", "hd-oct", "oct", "microscope", "microscopy", "fluorescent", "fish", "cohu-ccd", "lens", "camera")),
    "CARL": ("vendor_reference_metadata", ("carl zeiss", "zeiss meditec", "iol master", "visupac", "cirrus", "hd-oct", "oct", "microscope", "microscopy", "camera")),
    "VYSIS": ("vendor_reference_metadata", ("fish", "probe", "probes", "protocol", "hybridization")),
    "VINCI": ("vendor_reference_metadata", ("da vinci", "robot", "robotic", "surgical system", "intuitive surgical")),
    "ROCHE": ("vendor_reference_metadata", ("hoffmann-la roche", "hoffmann la roche", "tecentriq", "atezolizumab", "basel", "ag")),
    "ABBOTT": ("vendor_reference_metadata", ("perclose", "proglide", "pro-glide", "smc", "vascular closure")),
    "STRYKER": ("vendor_reference_metadata", ("neurovascular", "trevo", "surpass", "gdc", "gamma3", "intramedullary nail", "pressure monitor", "compartment pressure", "coil", "coils", "trident", "accolade", "acetabular cup", "femoral stem", "femoral prosthesis", "orthopaedic", "orthopedic", "surgical navigation", "endoscopy", "implant", "excelsior", "microcatheter", "xt-27")),
    "ZIMMER": ("vendor_reference_metadata", ("biomet", "dental", "implant", "prosthesis", "orthopedic", "orthopaedic", "knee", "hip")),
    "SOMANETICS": ("vendor_reference_metadata", ("invos", "cerebral oximeter", "oximeter", "near-infrared", "nirs")),
    "MAYFIELD": ("vendor_reference_metadata", ("clamp", "holder", "head holder", "skull clamp", "three-pin", "frame", "fixation")),
    "BAYER": ("vendor_reference_metadata", ("animal health", "baytril", "advantix", "seresto", "progynova", "hema-tek", "reandron", "schering", "centaur", "chemiluminometric", "assay", "contrast", "pharmaceutical", "gadovist", "magnevist", "xarelto", "aspirin", "healthcare", "drontal")),
    "SALSA": ("vendor_reference_metadata", ("mlpa", "probe amplification", "mrc holland", "stk11", "kit")),
    "GUIDANT": ("vendor_reference_metadata", ("stent", "device", "catheter", "endovascular", "implantable", "pacemaker", "icd")),
    "ETHICON": ("vendor_reference_metadata", ("suture", "stapler", "endopath", "endosurgery", "surgical", "prolene", "vicryl")),
    "TOMEY": ("vendor_reference_metadata", ("topographer", "corneal", "ophthalmic", "keratometer")),
    "MARQUE": ("vendor_reference_metadata", ("cell marque", "clone", "antibody", "immunohistochemical")),
    "GOODMAN": ("vendor_reference_metadata", ("lacrosse", "balloon catheter", "catheter")),
    "PHILIPS": ("vendor_reference_metadata", ("ingenuity", "ct simulation", "ct simulator", "scanner", "computed tomography")),
    "SIEMENS": ("vendor_reference_metadata", ("symphony", "1.5t", "mri", "magnetic resonance", "scanner")),
}


def _reconstruct_with_stable_dates(
    original_text: str,
    spans: list[PHISpan],
    *,
    date_shift_offset: int,
    date_shift_days: int,
) -> tuple[str, list[PHISpan], list[str]]:
    """Reconstruct final text with stable date shifting only.

    This is a compatibility wrapper around
    `_reconstruct_with_project_replacements(...)` for callers that only enable
    date-shift behavior.

    Args:
        original_text: Full original note text.
        spans: Normalized pyDeid spans with original-note offsets.
        date_shift_offset: Patient-specific day offset to apply to parseable dates.
        date_shift_days: Configured inclusive shift range, recorded for audit.

    Returns:
        `(deidentified_text, final_spans, warnings)`.
    """
    return _reconstruct_with_project_replacements(
        original_text,
        spans,
        date_shift_offset=date_shift_offset,
        date_shift_days=date_shift_days,
    )


def _reconstruct_with_project_replacements(
    original_text: str,
    spans: list[PHISpan],
    *,
    date_shift_offset: int | None = None,
    date_shift_days: int | None = None,
    patient_name_alias_profile: dict[str, Any] | None = None,
    patient_name_identity: dict[str, str] | None = None,
    provider_name_alias_profile: dict[str, Any] | None = None,
    provider_name_identities: dict[str, dict[str, str]] | None = None,
    protected_terms_profile: dict[str, Any] | None = None,
    shift_partial_month_day_dates: bool = True,
) -> tuple[str, list[PHISpan], list[str]]:
    """Rebuild final note text from original text and normalized spans.

    This function walks through the original note from left to right, copies
    unchanged text between spans, and inserts one selected replacement for each
    span. It also records final replacement offsets in each returned span's
    metadata.

    Args:
        original_text: Full original note text.
        spans: Normalized pyDeid spans. Their `start` and `end` offsets must
            refer to `original_text`.
        date_shift_offset: Optional patient-specific day offset. When provided,
            date-like spans receive stable date policy.
        date_shift_days: Optional configured inclusive date-shift range, recorded
            in audit metadata when date shifting is enabled.
        patient_name_alias_profile: Optional explicit patient-alias profile used
            to decide which pyDeid name spans receive stable patient-name
            surrogates.
        patient_name_identity: Optional deterministic fake patient identity.
        protected_terms_profile: Optional protected-term profile used to preserve
            clinical terms that pyDeid emitted as spans.

    Returns:
        A tuple `(final_text, final_spans, warnings)`:
        - `final_text`: reconstructed de-identified note text;
        - `final_spans`: copies of input spans with final replacement metadata;
        - `warnings`: sanitized reconstruction warnings.

    Raises:
        ValueError: If pyDeid spans have an unresolved mixed overlap, because
            reconstruction cannot safely decide which original text to copy or
            replace.

    Example:
        Original text:
            "Jane Smith visited on January 5, 2024."

        Input spans:
            - `Jane Smith`, label `NAME`, offsets 0:10
            - `January 5, 2024`, label `DATE`, offsets 22:37

        With stable patient-name and date-shift policies enabled, this function
        copies `" visited on "` unchanged and replaces only the two span ranges.
    """
    final_parts: list[str] = []
    final_spans: list[PHISpan] = []
    warnings: list[str] = []
    cursor = 0
    final_offset = 0
    sorted_spans, overlap_warnings = _prune_resolvable_overlapping_spans(
        spans,
        original_text=original_text,
    )
    warnings.extend(overlap_warnings)

    for span in sorted_spans:
        if span.start < cursor:
            # Fail closed. Overlapping spans make it unclear which original text
            # should be copied or replaced; silently continuing could leak PHI.
            raise ValueError("Overlapping pyDeid spans cannot be safely reconstructed.")

        unchanged_text = original_text[cursor : span.start]
        final_parts.append(unchanged_text)
        final_offset += len(unchanged_text)

        replacement_info = _project_replacement_for_span(
            span,
            all_spans=sorted_spans,
            date_shift_offset=date_shift_offset,
            original_text=original_text,
            patient_name_alias_profile=patient_name_alias_profile,
            patient_name_identity=patient_name_identity,
            provider_name_alias_profile=provider_name_alias_profile,
            provider_name_identities=provider_name_identities,
            protected_terms_profile=protected_terms_profile,
            shift_partial_month_day_dates=shift_partial_month_day_dates,
        )
        replacement_text, replacement_source, policy, policy_metadata = replacement_info
        if policy == "unparseable_date_placeholder":
            warnings.append("Unparseable pyDeid date span replaced with <DATE>.")
        replacement_start = final_offset
        final_parts.append(replacement_text)
        final_offset += len(replacement_text)
        replacement_end = final_offset

        metadata = dict(span.metadata)
        # These offsets point into the final ProjectPHI output text. They are
        # separate from original-note offsets and pyDeid-output surrogate offsets.
        metadata.update(
            {
                "replacement_source": replacement_source,
                "project_replacement": replacement_text,
                "project_replacement_start": replacement_start,
                "project_replacement_end": replacement_end,
            }
        )
        if date_shift_offset is not None:
            metadata["project_date_shift_range_days"] = date_shift_days
            metadata["project_date_shift_policy"] = policy
        if replacement_source == "project_stable_date_shift" and date_shift_offset is not None:
            metadata["project_date_shift_days"] = date_shift_offset
        if patient_name_alias_profile is not None and span.label == "NAME":
            metadata.update(_name_policy_metadata(replacement_source, policy))
        if provider_name_alias_profile is not None and span.label == "NAME":
            metadata.update(_provider_name_policy_metadata(replacement_source, policy))
        metadata.update(policy_metadata)

        final_spans.append(
            replace(
                span,
                action="replaced" if replacement_text != span.text else "preserved",
                replacement=replacement_text,
                metadata=metadata,
            )
        )
        cursor = span.end

    trailing_text = original_text[cursor:]
    final_parts.append(trailing_text)
    return "".join(final_parts), final_spans, warnings


def _prune_resolvable_overlapping_spans(
    spans: list[PHISpan],
    *,
    original_text: str = "",
) -> tuple[list[PHISpan], list[str]]:
    """Prune deterministic low-risk overlaps before reconstruction.

    pyDeid can occasionally emit nested or same-source/same-label overlapping
    spans. Reconstruction can safely proceed when one span is clearly the better
    replacement range. Mixed unresolved overlaps still fail closed downstream.
    """
    warnings: list[str] = []
    candidate_spans: list[PHISpan] = []
    for span in spans:
        if _span_inside_genomic_coordinate_token(span, original_text) and any(
            other is not span and _spans_overlap(span, other) for other in spans
        ):
            warnings.append("pyDeid span inside genomic coordinate dropped during reconstruction.")
            continue
        candidate_spans.append(span)

    accepted: list[PHISpan] = []
    for candidate in sorted(candidate_spans, key=lambda item: (item.start, item.end)):
        current: PHISpan | None = candidate
        while current is not None and accepted and current.start < accepted[-1].end:
            previous = accepted[-1]
            winner = _preferred_overlap_span(previous, current)
            if winner is previous:
                warnings.append("Overlapping pyDeid span dropped during reconstruction.")
                current = None
                break
            if winner is current:
                warnings.append("Overlapping pyDeid span dropped during reconstruction.")
                accepted.pop()
                continue
            return sorted(candidate_spans, key=lambda item: (item.start, item.end)), warnings
        if current is not None:
            accepted.append(current)
    return accepted, warnings


_GENOMIC_COORDINATE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"(?:chr)?(?:[0-9]{1,2}|X|Y|MT):[0-9,]{6,}[-\u2013][0-9,]{6,}"
    r"|[0-9,]{6,}[-\u2013][0-9,]{6,}"
    r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def _span_inside_genomic_coordinate_token(
    span: PHISpan,
    original_text: str,
) -> bool:
    """Return true for pyDeid spans wholly inside genomic coordinate tokens."""
    if not original_text:
        return False

    context = _span_context(original_text, span.start, span.end, window=220).casefold()
    if not _context_contains(context, _GENOMIC_COORDINATE_CONTEXT_TERMS):
        return False

    window_start = max(0, span.start - 48)
    window_end = min(len(original_text), span.end + 48)
    window = original_text[window_start:window_end]
    for match in _GENOMIC_COORDINATE_TOKEN_RE.finditer(window):
        start = window_start + match.start()
        end = window_start + match.end()
        if start <= span.start and span.end <= end:
            return True
    return False


def _spans_overlap(
    left: PHISpan,
    right: PHISpan,
) -> bool:
    """Return true when two original-note spans overlap."""
    return right.start < left.end and right.end > left.start


def _preferred_overlap_span(
    left: PHISpan,
    right: PHISpan,
) -> PHISpan | None:
    """Return the safer span to keep for a resolvable two-span overlap."""
    if left.start <= right.start and right.end <= left.end:
        return left
    if right.start <= left.start and left.end <= right.end:
        return right
    if left.label == right.label and left.source == right.source:
        left_len = left.end - left.start
        right_len = right.end - right.start
        if left_len != right_len:
            return left if left_len > right_len else right
        return left if (left.start, left.end) <= (right.start, right.end) else right
    return None


def _project_replacement_for_span(
    span: PHISpan,
    *,
    all_spans: list[PHISpan] | None = None,
    date_shift_offset: int | None = None,
    original_text: str = "",
    patient_name_alias_profile: dict[str, Any] | None = None,
    patient_name_identity: dict[str, str] | None = None,
    provider_name_alias_profile: dict[str, Any] | None = None,
    provider_name_identities: dict[str, dict[str, str]] | None = None,
    protected_terms_profile: dict[str, Any] | None = None,
    shift_partial_month_day_dates: bool = True,
) -> tuple[str, str, str, dict[str, Any]]:
    """Choose final replacement text and policy metadata for one span.

    Priority order is intentional:

    1. Protected clinical-term veto:
       preserve the original span text when pyDeid emitted a span that exactly
       matches a protected clinical term, or when a risky component is inside a
       configured clinical tool/scale phrase.

    2. Clinical abbreviation veto:
       preserve selected clinical abbreviations that pyDeid emits as facility
       acronyms inside longer clinical shorthand.

    3. Obstetric-history shorthand veto:
       preserve strict `G/P/A/L/T` notation that pyDeid emitted as a date,
       location, postal-code, or identifier-like span.

    4. Stable date policy:
       shift parseable full dates and month/year spans; preserve times,
       score/fraction notation, year-only spans, holidays, and seasons; replace
       unparseable date-like spans with `<DATE>`.

    5. Stable patient-name policy:
       replace explicit patient aliases with the deterministic fake patient
       identity.

    6. Stable provider-name policy:
       replace explicit provider aliases with deterministic fake provider
       identities. Single-token aliases require provider-role context. A
       lower-case action-word span immediately after an explicit provider alias
       can be preserved when following context supports a clinical verb read.

    7. Ordinary-token veto:
       preserve selected articles, pronouns, and clinical shorthand that pyDeid
       emitted as very short name spans when context supports a non-name read.

    8. Title-token-fragment veto:
       preserve non-identifying `Dr.` fragments when pyDeid split the title
       token itself into name spans in a strong title/name or role/title/name
       context.

    9. Title-context action-word veto:
       preserve narrow clinical action words that pyDeid emitted as
       title-derived name spans in `Dr.` contexts. Lower-case words use the
       base rule; capitalized words require following clinical-object context.

    10. pyDeid fallback:
       use pyDeid's replacement, or `<PHI>` if no replacement is available.

    Args:
        span: Current normalized pyDeid span.
        all_spans: Full normalized pyDeid span list for title-context checks.
        date_shift_offset: Optional patient-specific day offset. Date policy is
            enabled only when this is not `None`.
        original_text: Full original note text, used for split patient-alias
            context checks.
        patient_name_alias_profile: Optional explicit patient-alias profile.
        patient_name_identity: Optional deterministic fake patient identity.
        protected_terms_profile: Optional protected-term profile.

    Returns:
        `(replacement_text, replacement_source, policy, policy_metadata)`.

        Examples:
        - protected term: `("BI-RADS 2", "project_protected_clinical_term",
          "exact_normalized_span_match", {...})`
        - shifted date: `("January 15, 2024", "project_stable_date_shift",
          "shifted_natural_language_full_date", {})`
        - known patient alias: `("Alex Bennett", "project_stable_patient_name",
          "full", {})`
        - title-context action word: `("reviewed",
          "project_title_context_action_word_veto",
          "title_context_action_word_exact_match", {...})`
        - title-token fragment: `("D", "project_title_token_veto",
          "preserved_title_token_fragment", {...})`
        - unknown name: `("[**Name**]", "pyDeid", "unknown_name_pydeid", {})`

    Notes:
        This function does not mutate `span`.
    """
    protected_match = _protected_term_match(span, protected_terms_profile, original_text)
    if protected_match is not None:
        return (
            span.text,
            "project_protected_clinical_term",
            "exact_normalized_span_match",
            _protected_term_metadata(protected_match),
        )

    clinical_abbreviation_match = _clinical_abbreviation_veto_metadata(span, original_text)
    if clinical_abbreviation_match is not None:
        return (
            span.text,
            "project_clinical_abbreviation_veto",
            clinical_abbreviation_match["project_clinical_abbreviation_policy"],
            clinical_abbreviation_match,
        )

    obstetric_history_match = _obstetric_history_veto_metadata(span)
    if obstetric_history_match is not None:
        return (
            span.text,
            "project_obstetric_history_veto",
            obstetric_history_match["project_obstetric_history_policy"],
            obstetric_history_match,
        )

    # Date policy: shift parseable dates, preserve date-like spans that should
    # not receive day-level shifting, and use a safe placeholder for unparseable
    # date-like spans.
    if date_shift_offset is not None and _is_score_or_fraction_date_span(span, original_text):
        return (
            span.text,
            "preserved",
            "preserved_score_or_fraction",
            _score_or_fraction_date_metadata(),
        )

    if date_shift_offset is not None and _is_parseable_full_date_span(span):
        shifted_text = _shift_full_date_span(span, date_shift_offset)
        if shifted_text is not None:
            return (
                shifted_text,
                "project_stable_date_shift",
                _date_shift_policy_for_full_date_span(span),
                {},
            )

    if date_shift_offset is not None and _is_parseable_month_year_span(span):
        shifted_text = _shift_month_year_span(span, date_shift_offset)
        if shifted_text is not None:
            return (
                shifted_text,
                "project_stable_date_shift",
                "shifted_month_year",
                _date_shift_metadata_for_month_year_span(),
            )

    if (
        date_shift_offset is not None
        and shift_partial_month_day_dates
        and _is_parseable_partial_month_day_span(span)
    ):
        shifted_text = _shift_partial_month_day_span(span, date_shift_offset)
        if shifted_text is not None:
            return (
                shifted_text,
                "project_stable_date_shift",
                "shifted_partial_month_day",
                _date_shift_metadata_for_partial_month_day_span(),
            )

    if date_shift_offset is not None and _is_time_span(span):
        return span.text, "preserved", "preserved_time", {}
    if date_shift_offset is not None and _is_year_only_span(span):
        return span.text, "preserved", "preserved_year_only", {}
    if date_shift_offset is not None and _is_holiday_or_season_span(span):
        return span.text, "preserved", "preserved_holiday_or_season", {}
    if date_shift_offset is not None and _is_date_like_span(span):
        return "<DATE>", "project_stable_date_shift", "unparseable_date_placeholder", {}

    # Patient-name policy: only explicit patient aliases receive the stable fake
    # patient identity. Unknown names remain pyDeid replacements.
    if patient_name_alias_profile is not None and patient_name_identity is not None and span.label == "NAME":
        name_replacement = _project_patient_name_replacement(
            span,
            original_text=original_text,
            alias_profile=patient_name_alias_profile,
            identity=patient_name_identity,
        )
        if name_replacement is not None:
            replacement_text, match_type = name_replacement
            replacement_source = (
                "project_residual_patient_alias"
                if span.source == "ProjectPHI.residual_alias"
                else "project_stable_patient_name"
            )
            return replacement_text, replacement_source, match_type, {}

    if (
        provider_name_alias_profile is not None
        and provider_name_identities is not None
        and span.label == "NAME"
    ):
        provider_replacement = _project_provider_name_replacement(
            span,
            original_text=original_text,
            provider_alias_profile=provider_name_alias_profile,
            provider_name_identities=provider_name_identities,
        )
        if provider_replacement is not None:
            replacement_text, match_type = provider_replacement
            replacement_source = (
                "project_residual_provider_alias"
                if span.source == "ProjectPHI.residual_provider_alias"
                else "project_stable_provider_name"
            )
            return replacement_text, replacement_source, match_type, {}

        provider_action_match = _project_provider_adjacent_action_word_metadata(
            span,
            original_text=original_text,
            spans=all_spans or [],
            provider_alias_profile=provider_name_alias_profile,
            provider_name_identities=provider_name_identities,
        )
        if provider_action_match is not None:
            return (
                span.text,
                "project_provider_adjacent_action_word_veto",
                provider_action_match["project_provider_action_policy"],
                provider_action_match,
            )

    decimal_code_match = _decimal_code_contact_veto_metadata(span, original_text)
    if decimal_code_match is not None:
        return (
            span.text,
            "project_decimal_code_veto",
            decimal_code_match["project_decimal_code_policy"],
            decimal_code_match,
        )

    clinical_code_match = _clinical_code_veto_metadata(span, original_text)
    if clinical_code_match is not None:
        return (
            span.text,
            "project_clinical_code_veto",
            clinical_code_match["project_clinical_code_policy"],
            clinical_code_match,
        )

    ordinary_clinical_prose_match = _ordinary_clinical_prose_veto_metadata(
        span,
        original_text,
    )
    if ordinary_clinical_prose_match is not None:
        return (
            span.text,
            "project_ordinary_clinical_prose_veto",
            ordinary_clinical_prose_match["project_ordinary_clinical_prose_policy"],
            ordinary_clinical_prose_match,
        )

    ordinary_token_match = _ordinary_token_veto_metadata(span, original_text)
    if ordinary_token_match is not None:
        return (
            span.text,
            "project_ordinary_token_veto",
            ordinary_token_match["project_ordinary_token_policy"],
            ordinary_token_match,
        )

    title_token_match = _title_token_fragment_match(
        span,
        original_text=original_text,
        spans=all_spans or [],
    )
    if title_token_match is not None:
        return (
            span.text,
            "project_title_token_veto",
            title_token_match["project_title_token_policy"],
            _title_token_fragment_metadata(title_token_match),
        )

    title_context_match = _title_context_action_word_match(
        span,
        original_text=original_text,
        spans=all_spans or [],
        patient_name_alias_profile=patient_name_alias_profile,
    )
    if title_context_match is not None:
        return (
            span.text,
            "project_title_context_action_word_veto",
            title_context_match["project_title_context_policy"],
            _title_context_action_word_metadata(title_context_match),
        )

    if patient_name_alias_profile is not None and patient_name_identity is not None and span.label == "NAME":
        return span.replacement or "<PHI>", "pyDeid", "unknown_name_pydeid", {}

    if provider_name_alias_profile is not None and provider_name_identities is not None and span.label == "NAME":
        return span.replacement or "<PHI>", "pyDeid", "unknown_name_pydeid", {}

    # Final fallback for all other spans.
    return span.replacement or "<PHI>", "pyDeid", "pydeid_replacement", {}


def _clinical_code_veto_metadata(
    span: PHISpan,
    original_text: str,
) -> dict[str, str] | None:
    """Return metadata for compact clinical codes and semantic phrases.

    The rule is pyDeid-span-local. It preserves values whose syntax and bounded
    context strongly indicate clinical meaning, leaving production-specific
    identifiers to explicit lists or custom regexes.
    """
    token = span.text.strip()
    context = _span_context(original_text, span.start, span.end, window=140).casefold()
    broad_context = _span_context(original_text, span.start, span.end, window=240).casefold()

    if span.label in {"TIME", "CONTACT", "ID"} and _span_inside_genomic_coordinate_token(
        span,
        original_text,
    ):
        return {
            "project_clinical_code_policy": "preserved_contextual_clinical_code",
            "project_clinical_code": token,
            "project_clinical_code_context": "genomic_coordinate_token",
        }

    if span.label not in {"NAME", "LOCATION", "HOSPITAL", "ID", "PHI"}:
        return None

    if _GCS_COMPONENT_RE.match(token) and _context_contains(context, _GCS_CONTEXT_TERMS):
        return {
            "project_clinical_code_policy": "preserved_compact_clinical_code",
            "project_clinical_code": token,
            "project_clinical_code_context": "glasgow_coma_scale",
        }

    if _TNM_STAGE_RE.match(token) and _context_contains(broad_context, _TNM_CONTEXT_TERMS):
        return {
            "project_clinical_code_policy": "preserved_compact_clinical_code",
            "project_clinical_code": token,
            "project_clinical_code_context": "tnm_staging",
        }

    if _DURATION_TRAVEL_RE.match(token) and _context_contains(
        broad_context,
        ("altitude", "during a", "exposure", "travel", "visual", "symptoms"),
    ):
        return {
            "project_clinical_code_policy": "preserved_clinical_duration_phrase",
            "project_clinical_code": token,
            "project_clinical_code_context": "duration_or_exposure_phrase",
        }

    if _GENOMIC_COORDINATE_RANGE_RE.match(token) and _context_contains(
        broad_context,
        _GENOMIC_COORDINATE_CONTEXT_TERMS,
    ):
        return {
            "project_clinical_code_policy": "preserved_contextual_clinical_code",
            "project_clinical_code": token,
            "project_clinical_code_context": "genomic_coordinate_range",
        }

    normalized = re.sub(r"[^A-Za-z0-9]+", "", token).upper()
    if (
        token == "URA"
        and _span_has_nonword_boundaries(span, original_text)
        and _context_contains(
            broad_context,
            ("upper renal artery", "renal artery", "angiogram", "aneurysm", "kidney"),
        )
    ):
        return {
            "project_clinical_code_policy": "preserved_contextual_clinical_code",
            "project_clinical_code": token,
            "project_clinical_code_context": "upper_renal_artery_abbreviation",
        }

    rule = _CLINICAL_CODE_CONTEXT_RULES.get(normalized)
    if rule is not None:
        context_name, context_terms = rule
        if _context_contains(broad_context, context_terms):
            return {
                "project_clinical_code_policy": "preserved_contextual_clinical_code",
                "project_clinical_code": token,
                "project_clinical_code_context": context_name,
            }

    vendor_rule = _VENDOR_REFERENCE_CONTEXT_RULES.get(normalized)
    if vendor_rule is not None:
        context_name, context_terms = vendor_rule
        if _context_contains(broad_context, context_terms):
            return {
                "project_clinical_code_policy": "preserved_vendor_reference_metadata",
                "project_clinical_code": token,
                "project_clinical_code_context": context_name,
            }

    return None


def _ordinary_clinical_prose_veto_metadata(
    span: PHISpan,
    original_text: str,
) -> dict[str, str] | None:
    """Return metadata for low-risk ordinary clinical prose false positives."""
    if span.label != "NAME":
        return None

    token = span.text.strip()
    normalized = token.casefold()
    rule = _ORDINARY_CLINICAL_PROSE_TERMS.get(normalized)
    if rule is None:
        return None

    context_name, context_terms = rule
    context = _span_context(original_text, span.start, span.end, window=90).casefold()
    if not _context_contains(context, context_terms):
        return None

    return {
        "project_ordinary_clinical_prose_policy": "preserved_contextual_clinical_prose",
        "project_ordinary_clinical_prose": token,
        "project_ordinary_clinical_prose_context": context_name,
    }


def _ordinary_token_veto_metadata(
    span: PHISpan,
    original_text: str,
) -> dict[str, str] | None:
    """Return metadata for very narrow common-token name false positives.

    This is not a name detector. It only preserves selected pyDeid-emitted
    `NAME` spans whose whole text is a common article/pronoun or the observed
    nursing-home shorthand `NH`, and only when simple local guards suggest that
    preserving the token is safer than replacing it.
    """
    if span.label != "NAME":
        return None

    token = span.text
    normalized = token.casefold()
    if normalized in _ORDINARY_ARTICLE_PRONOUN_TOKENS:
        if _looks_like_initial_or_case_label_context(span, original_text):
            return None
        return {
            "project_ordinary_token_policy": "preserved_pronoun_or_article",
            "project_ordinary_token": token,
            "project_ordinary_token_category": "pronoun_or_article",
        }

    if token == "NH" and _has_nursing_home_context(span, original_text):
        return {
            "project_ordinary_token_policy": "preserved_clinical_shorthand",
            "project_ordinary_token": token,
            "project_ordinary_token_category": "nursing_home",
        }

    if token == "t" and _is_split_at_before_numeric_or_time_context(span, original_text):
        return {
            "project_ordinary_token_policy": "preserved_split_at_fragment",
            "project_ordinary_token": token,
            "project_ordinary_token_category": "split_at_numeric_time_context",
        }

    return None


def _decimal_code_contact_veto_metadata(
    span: PHISpan,
    original_text: str,
) -> dict[str, str] | None:
    """Return metadata for dotted numeric code fragments misread as phones."""
    if span.label != "CONTACT":
        return None
    if "telephone/fax" not in " ".join(span.pydeid_types or []).casefold():
        return None

    if _is_long_float_measurement_fragment(span, original_text):
        return {
            "project_decimal_code_policy": "preserved_decimal_like_code_fragment",
            "project_decimal_code_context": "long_float_measurement_context",
        }

    span_digits = _dotted_numeric_groups(span.text)
    if span_digits is None:
        return None

    if _has_dotted_numeric_colon_continuation(span, original_text):
        return {
            "project_decimal_code_policy": "preserved_decimal_like_code_fragment",
            "project_decimal_code_context": "colon_dotted_numeric_continuation",
        }

    if not _looks_like_dotted_phone_groups(span_digits):
        return {
            "project_decimal_code_policy": "preserved_decimal_like_code_fragment",
            "project_decimal_code_context": "non_phone_dotted_grouping",
        }

    return None


def _dotted_numeric_groups(text: str) -> tuple[int, ...] | None:
    """Return digit group lengths for a whole dotted numeric token."""
    stripped = text.strip(" \t\r\n()[]{}")
    if "." not in stripped:
        return None
    parts = stripped.split(".")
    if len(parts) < 2 or not all(part.isdigit() for part in parts):
        return None
    return tuple(len(part) for part in parts)


def _looks_like_dotted_phone_groups(groups: tuple[int, ...]) -> bool:
    """Return true for dotted phone-number digit grouping ProjectPHI should keep replacing."""
    return groups == (3, 3, 4) or groups == (1, 3, 3, 4)


def _has_dotted_numeric_colon_continuation(
    span: PHISpan,
    original_text: str,
) -> bool:
    """Return true when a dotted span is followed by colon+dotted numeric text."""
    after = original_text[span.end : min(len(original_text), span.end + 32)]
    return re.match(r"^\s*:\s*\d+(?:\.\d+)+", after) is not None


def _is_long_float_measurement_fragment(
    span: PHISpan,
    original_text: str,
) -> bool:
    """Return true for long decimal fragments in measurement context."""
    token = span.text.strip(" \t\r\n()[]{}")
    context = _span_context(original_text, span.start, span.end, window=120).casefold()
    if not _has_long_float_measurement_context(context):
        return False

    if re.fullmatch(r"\d+\.\d{8,}", token):
        return True

    if not _LONG_FLOAT_FRAGMENT_RE.fullmatch(token):
        return False

    before = original_text[max(0, span.start - 3) : span.start]
    after = original_text[span.end : min(len(original_text), span.end + 3)]
    return (
        bool(re.search(r"\d\.$", before))
        or bool(re.match(r"^\.\d", after))
    )


def _has_long_float_measurement_context(context: str) -> bool:
    """Return true for measurement cues without matching `cm`/`mm` inside words."""
    if _context_contains(
        context,
        tuple(term for term in _LONG_FLOAT_MEASUREMENT_CONTEXT_TERMS if term not in {"cm", "mm"}),
    ):
        return True
    return re.search(r"(?<![a-z0-9])(?:cm|mm)(?![a-z0-9])", context) is not None


def _clinical_abbreviation_veto_metadata(
    span: PHISpan,
    original_text: str,
) -> dict[str, str] | None:
    """Return metadata when a pyDeid span is clinical shorthand.

    This project veto is intentionally narrow and span-local. It handles
    observed abbreviation false positives such as `PMH` in medical-history
    context, `PMH` inside `PMHx`, and short molecular/clinical abbreviations
    only when bounded local context supports a clinical reading.
    """
    token = span.text.upper()
    context = _span_context(original_text, span.start, span.end).casefold()

    if token == "PMH" and _site_acronym_type(span):
        if span.end < len(original_text) and original_text[span.end] in {"x", "X"}:
            return {
                "project_clinical_abbreviation_policy": "preserved_pmhx_site_acronym_overlap",
                "project_clinical_abbreviation": original_text[span.start : span.end + 1],
            }
        if _context_contains(context, _PMH_CONTEXT_TERMS):
            return {
                "project_clinical_abbreviation_policy": "preserved_clinical_abbreviation_context",
                "project_clinical_abbreviation": span.text,
                "project_clinical_abbreviation_context": "past_medical_history",
            }

    if token == "MSH":
        abbreviation = span.text
        if span.end < len(original_text) and original_text[span.end] in {"2", "6"}:
            abbreviation = original_text[span.start : span.end + 1]
        if abbreviation.upper() in {"MSH2", "MSH6"} or _context_contains(context, _MSH_CONTEXT_TERMS):
            return {
                "project_clinical_abbreviation_policy": "preserved_clinical_abbreviation_context",
                "project_clinical_abbreviation": abbreviation,
                "project_clinical_abbreviation_context": "mismatch_repair",
            }

    if token in {"NIA", "AA"} and _is_nia_aa_component(span, original_text):
        return {
            "project_clinical_abbreviation_policy": (
                "preserved_clinical_abbreviation_component_context"
            ),
            "project_clinical_abbreviation": span.text,
            "project_clinical_abbreviation_context": "nia_aa_criteria",
        }

    context_rules = {
        "SAH": ("subarachnoid_hemorrhage", _SAH_CONTEXT_TERMS),
        "WES": ("whole_exome_sequencing", _WES_CONTEXT_TERMS),
        "SAM": ("subaortic_membrane", _SAM_CONTEXT_TERMS),
        "AMAN": ("acute_motor_axonal_neuropathy", _AMAN_CONTEXT_TERMS),
        "NIA": ("nia_aa_criteria", _NIA_AA_CONTEXT_TERMS),
    }
    if token in context_rules:
        context_name, context_terms = context_rules[token]
        if _context_contains(context, context_terms) or _context_contains(
            _span_context(original_text, span.start, span.end, window=220).casefold(),
            context_terms,
        ):
            return {
                "project_clinical_abbreviation_policy": "preserved_clinical_abbreviation_context",
                "project_clinical_abbreviation": span.text,
                "project_clinical_abbreviation_context": context_name,
            }

    return None


def _obstetric_history_veto_metadata(
    span: PHISpan,
) -> dict[str, str] | None:
    """Return metadata for strict obstetric-history shorthand preservation."""
    normalized = re.sub(r"\s+", "", span.text)
    if not any(pattern.match(normalized) for pattern in _OBSTETRIC_HISTORY_PATTERNS):
        return None

    return {
        "project_obstetric_history_policy": "preserved_strict_obstetric_shorthand",
        "project_obstetric_history_pattern": "gpa_or_gtpal",
    }


def _site_acronym_type(span: PHISpan) -> bool:
    """Return true for pyDeid site-acronym type labels."""
    return "site acronym" in " ".join(span.pydeid_types or []).lower()


def _context_contains(context: str, terms: tuple[str, ...]) -> bool:
    """Return true when any configured cue appears in casefolded context."""
    return any(term in context for term in terms)


def _span_has_nonword_boundaries(span: PHISpan, original_text: str) -> bool:
    """Return true when a span is not embedded in a larger word token."""
    before = original_text[span.start - 1] if span.start > 0 else ""
    after = original_text[span.end] if span.end < len(original_text) else ""
    return (
        (not before or not (before.isalnum() or before == "_"))
        and (not after or not (after.isalnum() or after == "_"))
    )


def _is_nia_aa_component(
    span: PHISpan,
    original_text: str,
) -> bool:
    """Return true when `NIA`/`AA` is a pyDeid span inside `NIA-AA`."""
    window = original_text[max(0, span.start - 4) : min(len(original_text), span.end + 4)]
    absolute_offset = max(0, span.start - 4)
    for match in re.finditer(r"(?<![A-Za-z])NIA-AA(?![A-Za-z])", window, re.IGNORECASE):
        start = absolute_offset + match.start()
        end = absolute_offset + match.end()
        if start <= span.start and span.end <= end:
            return True
    return False


def _span_context(
    text: str,
    start: int,
    end: int,
    *,
    window: int = 90,
) -> str:
    """Return bounded local context around a pyDeid span."""
    return text[max(0, start - window) : min(len(text), end + window)]


def _looks_like_initial_or_case_label_context(
    span: PHISpan,
    original_text: str,
) -> bool:
    """Return true when a short token is likely an initial/case label."""
    before = original_text[max(0, span.start - 24) : span.start]
    after = original_text[span.end : min(len(original_text), span.end + 24)]
    before_words = before.lower().replace(".", " ").split()
    previous_word = before_words[-1] if before_words else ""

    if previous_word in _INITIAL_CONTEXT_PREFIXES:
        return True
    if _previous_token_is_title_prefix(before):
        return True
    if after.startswith(".") or after.startswith(" ."):
        return True
    if after.startswith("-"):
        return True
    if len(span.text) == 1 and after[:1].isupper():
        return True
    return False


def _previous_token_is_title_prefix(text_before: str) -> bool:
    """Return true for title-cased prefixes without treating `MR.` as `Mr.`."""
    tokens = text_before.split()
    if not tokens:
        return False
    return tokens[-1] in _TITLE_INITIAL_CONTEXT_PREFIXES


def _has_nursing_home_context(
    span: PHISpan,
    original_text: str,
) -> bool:
    """Return true for narrow nursing-home shorthand contexts around `NH`."""
    before = original_text[max(0, span.start - 32) : span.start].lower()
    after = original_text[span.end : min(len(original_text), span.end + 32)].lower()
    return any(after.startswith(term) for term in _NH_CONTEXT_AFTER) or any(
        term in before for term in _NH_CONTEXT_BEFORE
    )


def _is_split_at_before_numeric_or_time_context(
    span: PHISpan,
    original_text: str,
) -> bool:
    """Return true for pyDeid splitting `at` before numeric/time context."""
    if span.start < 1 or original_text[span.start - 1] != "a":
        return False

    before_a_index = span.start - 2
    if before_a_index >= 0 and (
        original_text[before_a_index].isalnum() or original_text[before_a_index] == "_"
    ):
        return False

    after = original_text[span.end : min(len(original_text), span.end + 40)]
    return re.match(
        r"^\s+(?:"
        r"\d+(?:[./:]\d+)?(?:-\w+)?"
        r"|noon\b"
        r"|midnight\b"
        r")",
        after,
        re.IGNORECASE,
    ) is not None
