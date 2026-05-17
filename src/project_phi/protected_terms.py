"""Span-local protected clinical terminology helpers.

Protected terms are semantic-preservation vetoes, not PHI detectors.

They are used only after pyDeid has already emitted a span. This module checks
whether the detected span text exactly matches a configured protected clinical
term after light normalization. It never scans the full note, creates new spans,
or changes pyDeid's detection/pruning behavior.
"""

from __future__ import annotations

import re
from typing import Any

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
            "nipple discharge",
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
            "triple negative",
            "triple-negative",
            "hormone receptor positive",
            "hormone receptor-positive",
            "estrogen receptor positive",
            "estrogen receptor-positive",
            "progesterone receptor positive",
            "progesterone receptor-positive",
        ],
    },
    "staging_recurrence_metastasis": {
        "category": "staging_recurrence_metastasis",
        "terms": [
            "cT1N0M0",
            "cT2N0M0",
            "cT2N1M0",
            "pT1N0M0",
            "pT2N0M0",
            "pT2N1M0",
            "T1N0M0",
            "T2N0M0",
            "T2N1M0",
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
            "adjuvant radiation",
            "radiation therapy",
            "regional nodes",
            "left breast and regional nodes",
            "dose-dense AC-T",
            "AC-T chemotherapy",
            "chemotherapy",
            "adjuvant chemotherapy",
            "neoadjuvant chemotherapy",
            "radiation",
        ],
    },
}

# Built-in protected terms are manually curated, general, and non-site-specific.
# They are intended to reduce clinically harmful false positives in breast
# imaging / oncology notes. They should not contain patient names, site-specific
# identifiers, local aliases, accession formats, MRN formats, or other PHI-like
# strings.


def _build_protected_terms_profile(
    protected_clinical_terms,
    *,
    include_builtin_protected_clinical_terms: bool,
) -> dict[str, Any] | None:
    """Validate protected-term config and build a normalized exact-match index.

    Runtime config shape:
        {
            "rule_id": {
                "category": "clinical_category",
                "terms": ["term one", "term two"]
            }
        }

    Args:
        protected_clinical_terms: Optional runtime protected-term rules. Keys are
            rule IDs. Values must contain a nonempty `category` string and a
            nonempty list of term strings.
        include_builtin_protected_clinical_terms: Whether to include the curated
            built-in protected clinical terminology list.

    Returns:
        A profile dictionary with:
        - `terms`: normalized term text mapped to rule/category provenance;
        - `rule_ids`: configured rule IDs included in the profile.

        Returns `None` when no built-in or runtime terms are enabled.

    Raises:
        ValueError: If the runtime config has an invalid shape, empty rule IDs,
            empty categories, empty term lists, non-string terms, or duplicate
            normalized terms across different rules.

    Notes:
        This profile is used only for exact whole-span matching against pyDeid
        spans. It is not used to scan the full note.
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

        terms = rule_config.get("terms")
        if not isinstance(terms, list) or not terms:
            raise ValueError("protected_clinical_terms rule config requires at least one term.")

        rule_ids.append(sanitized_rule_id)
        for term in terms:
            if not isinstance(term, str) or not term.strip():
                raise ValueError("protected_clinical_terms terms must be nonempty strings.")
            normalized = _normalize_protected_term(term)
            existing = term_index.get(normalized)
            if existing is not None and existing["rule_id"] != sanitized_rule_id:
                # A normalized term can only belong to one rule. Otherwise audit
                # provenance would be ambiguous.
                raise ValueError("protected_clinical_terms contains duplicate normalized terms.")
            term_index[normalized] = {
                "rule_id": sanitized_rule_id,
                "category": category,
            }

    return {"terms": term_index, "rule_ids": rule_ids}


def _protected_term_match(
    span: PHISpan,
    protected_terms_profile: dict[str, Any] | None,
) -> dict[str, str] | None:
    """Return rule/category provenance if a span exactly matches a protected term.

    Args:
        span: pyDeid-emitted span to check. Only `span.text` is normalized and
            matched; the surrounding note text is not scanned.
        protected_terms_profile: Profile returned by `_build_protected_terms_profile`,
            or `None` when protected terms are disabled.

    Returns:
        The matching rule/category metadata, or `None` if there is no exact
        normalized whole-span match.
    """
    if not protected_terms_profile:
        return None
    return protected_terms_profile["terms"].get(_normalize_protected_term(span.text))


def _protected_term_metadata(
    match: dict[str, str],
) -> dict[str, str]:
    """Convert a protected-term match into span/audit metadata.

    Args:
        match: Rule/category provenance returned by `_protected_term_match`.

    Returns:
        Metadata fields recorded on the span and later emitted to audit CSV:
        - `project_protected_term_policy`: matching policy used;
        - `project_protected_term_rule_id`: protected-term rule ID;
        - `project_protected_term_category`: protected-term category.
    """
    return {
        "project_protected_term_policy": "exact_normalized_span_match",
        "project_protected_term_rule_id": match["rule_id"],
        "project_protected_term_category": match["category"],
    }


def _normalize_protected_term(
    value: str,
) -> str:
    """Normalize a configured term or span text for exact matching.

    Normalization is intentionally light:
    - trim surrounding whitespace;
    - casefold for case-insensitive matching;
    - remove a small set of leading/trailing punctuation;
    - collapse repeated whitespace.

    This does not perform stemming, fuzzy matching, substring matching, or full
    note scanning.
    """
    text = value.strip().casefold()
    # Strip simple boundary punctuation that pyDeid spans may include, while
    # preserving punctuation inside clinical terms such as BI-RADS or HER2-negative.
    text = text.strip("([")
    text = text.rstrip(".,;:)]")
    return re.sub(r"\s+", " ", text).strip()
