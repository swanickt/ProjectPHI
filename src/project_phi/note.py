"""Single-note ProjectPHI orchestration around pyDeid.

This module exposes the main single-note workflow: `deidentify_note(...)`.

pyDeid remains responsible for:
- PHI detection;
- pyDeid pruning behavior;
- built-in regex/list matching;
- custom regex matching;
- initial surrogate generation.

ProjectPHI adds optional policy layers around pyDeid:
- custom regex config validation/provenance;
- span normalization into `PHISpan`;
- stable per-patient date shifting;
- stable patient-name aliases for explicitly configured patient aliases;
- protected clinical-term preservation;
- final reconstruction from original-note offsets when project policies are enabled.

Basic example:
    result = deidentify_note(
        "Patient Jane Smith was seen on January 5, 2024.",
        patient_id="P001",
        note_id="N001",
    )

Stable date-shift example:
    result = deidentify_note(
        "Follow-up scheduled for January 5, 2024.",
        patient_id="P001",
        stable_date_shift=True,
        date_shift_secret_env_var="PROJECTPHI_DATE_SHIFT_SECRET",
    )

Stable patient-name example:
    result = deidentify_note(
        "Jane Smith was seen by Dr Brown.",
        patient_id="P001",
        stable_patient_name_surrogates=True,
        patient_aliases=["Jane Smith", "Jane", "Ms Smith"],
        patient_name_secret_env_var="PROJECTPHI_PATIENT_NAME_SECRET",
    )

Protected clinical-term example:
    result = deidentify_note(
        "BI-RADS 2 was documented.",
        protected_clinical_terms={
            "birads": {
                "category": "breast_imaging",
                "terms": ["BI-RADS 2"],
            }
        },
    )

Security notes:
- `include_original_text=False` by default, so the returned result does not keep
  the raw note text unless explicitly requested.
- Secrets are used only to derive stable replacements. They are not stored in
  result metadata, span metadata, warnings, or audit output.
- pyDeid custom regex patterns are not stored in normalized span metadata.
"""

from __future__ import annotations

from typing import Iterable

from .custom_regex import _build_pydeid_custom_regexes
from .date_shift import (
    _requested_types_include_dates,
    _resolve_date_shift_secret,
    _stable_date_shift_offset,
)
from .models import DeidentificationResult
from .normalization import normalize_surrogates
from .patient_names import (
    _build_patient_alias_profile,
    _merge_patient_alias_custom_names,
    _requested_types_include_names,
    _resolve_patient_name_secret,
    _stable_patient_name_identity,
)
from .protected_terms import _build_protected_terms_profile
from .pydeid_client import DEFAULT_PYDEID_TYPES, run_pydeid_deid_string
from .reconstruction import _reconstruct_with_project_replacements


def deidentify_note(
    note_text: str,
    *,
    patient_id: str | None = None,
    encounter_id: str | None = None,
    note_id: str | None = None,
    include_original_text: bool = False,
    types: Iterable[str] | None = None,
    custom_dr_first_names: set[str] | None = None,
    custom_dr_last_names: set[str] | None = None,
    custom_patient_first_names: set[str] | None = None,
    custom_patient_last_names: set[str] | None = None,
    named_entity_recognition: bool = False,
    stable_date_shift: bool = False,
    date_shift_secret: str | bytes | None = None,
    date_shift_secret_env_var: str | None = None,
    date_shift_days: int = 45,
    stable_patient_name_surrogates: bool = False,
    patient_aliases: Iterable[str] | None = None,
    patient_name_secret: str | bytes | None = None,
    patient_name_secret_env_var: str | None = None,
    custom_regexes=None,
    protected_clinical_terms=None,
    include_builtin_protected_clinical_terms: bool = True,
) -> DeidentificationResult:
    """De-identify one note with pyDeid plus optional ProjectPHI policies.

    This is the main public single-note workflow. It calls pyDeid once, normalizes
    pyDeid's surrogate records into `PHISpan` objects, and optionally reconstructs
    the final de-identified text from original-note offsets when ProjectPHI
    replacement policies are enabled.

    Args:
        note_text: Original single-note text passed to pyDeid.
        patient_id: Optional stable patient key. Required when stable date
            shifting or stable patient-name surrogates are enabled. Also copied
            into result/span metadata for audit context.
        encounter_id: Optional encounter identifier copied into metadata.
        note_id: Optional note identifier copied into metadata.
        include_original_text: Whether to retain the original note text in the
            returned in-memory result. Defaults to `False`.
        types: pyDeid PHI categories to request. If omitted,
            `DEFAULT_PYDEID_TYPES` is used.
        custom_dr_first_names: Extra doctor first-name tokens passed through to
            pyDeid.
        custom_dr_last_names: Extra doctor last-name tokens passed through to
            pyDeid.
        custom_patient_first_names: Extra patient first-name tokens passed
            through to pyDeid.
        custom_patient_last_names: Extra patient last-name tokens passed through
            to pyDeid.
        named_entity_recognition: pyDeid NER flag. This baseline requires
            `False`; passing `True` raises `ValueError`.
        stable_date_shift: Whether to replace parseable pyDeid-detected dates
            using a deterministic patient-specific day offset.
        date_shift_secret: Direct secret for stable date shifting. Useful for
            tests; environment variables are preferred for runtime use.
        date_shift_secret_env_var: Environment variable containing the date-shift
            secret. Used only when `date_shift_secret` is not provided.
        date_shift_days: Inclusive maximum date-shift range. For example, `45`
            maps each patient to an offset in `[-45, +45]`.
        stable_patient_name_surrogates: Whether explicit patient aliases should
            receive one deterministic fake identity for the patient.
        patient_aliases: Explicit aliases for this patient, such as
            `["Jane Smith", "Jane", "Ms Smith"]`. Required when stable patient
            name surrogates are enabled.
        patient_name_secret: Direct secret for stable patient-name generation.
            Useful for tests; environment variables are preferred for runtime use.
        patient_name_secret_env_var: Environment variable containing the
            patient-name secret. Used only when `patient_name_secret` is not
            provided.
        custom_regexes: ProjectPHI custom regex config. ProjectPHI validates the
            config and converts it to pyDeid custom regex objects; pyDeid still
            performs the matching.
        protected_clinical_terms: Runtime protected-term config used as a
            span-local false-positive veto. These terms are checked only against
            pyDeid-emitted spans; the full note is not scanned.
        include_builtin_protected_clinical_terms: Whether to include the curated
            built-in protected clinical terminology list.

    Returns:
        A `DeidentificationResult` containing:
        - final de-identified text;
        - normalized spans with replacement/audit metadata;
        - sanitized warnings;
        - note-level metadata about selected options and provenance.

    Raises:
        ValueError: If unsupported NER is requested, if stable date shifting is
            enabled without date detection, if stable patient-name surrogates are
            enabled without name detection, or if required secrets/aliases are
            missing.

    Examples:
        Default pyDeid-backed de-identification:
            result = deidentify_note(
                "Patient Jane Smith was seen on January 5, 2024.",
                patient_id="P001",
                note_id="N001",
            )

        Keep original text in memory for tests/debugging:
            result = deidentify_note(
                "Patient Jane Smith was seen.",
                include_original_text=True,
            )

        Request a narrower pyDeid type set:
            result = deidentify_note(
                "Patient Jane Smith was seen on January 5, 2024.",
                types=["names", "dates"],
            )

        Stable date shifting:
            result = deidentify_note(
                "Follow-up scheduled for January 5, 2024.",
                patient_id="P001",
                stable_date_shift=True,
                date_shift_secret_env_var="PROJECTPHI_DATE_SHIFT_SECRET",
                date_shift_days=45,
            )

        Stable patient-name aliases:
            result = deidentify_note(
                "Jane Smith was seen by Dr Brown.",
                patient_id="P001",
                stable_patient_name_surrogates=True,
                patient_aliases=["Jane Smith", "Jane", "Ms Smith"],
                patient_name_secret_env_var="PROJECTPHI_PATIENT_NAME_SECRET",
            )

        Custom regex config:
            result = deidentify_note(
                "Synthetic MRN WB-1234567 was found.",
                custom_regexes={
                    "synthetic_wb_mrn": {
                        "phi_type": "Synthetic WB MRN",
                        "pattern": r"\\bWB-\\d{7}\\b",
                        "replacement": "<SYNTHETIC_MRN>",
                    }
                },
            )

        Runtime protected clinical terms:
            result = deidentify_note(
                "BI-RADS 2 was documented.",
                protected_clinical_terms={
                    "birads": {
                        "category": "breast_imaging",
                        "terms": ["BI-RADS 2"],
                    }
                },
            )
    """
    # pyDeid NER is intentionally disabled. The wrapper relies
    # on pyDeid's regex/list behavior plus explicit ProjectPHI policies.
    if named_entity_recognition:
        raise ValueError("NER is not enabled in the first project milestone.")
    # Stable project policies require the corresponding pyDeid detector category.
    # ProjectPHI does not independently detect dates or names.
    requested_types = list(types) if types is not None else list(DEFAULT_PYDEID_TYPES)
    if stable_date_shift and not _requested_types_include_dates(requested_types):
        raise ValueError("stable_date_shift=True requires pyDeid date detection in `types`.")
    if stable_patient_name_surrogates and not _requested_types_include_names(requested_types):
        raise ValueError(
            "stable_patient_name_surrogates=True requires pyDeid name detection in `types`."
        )

    date_shift_secret_bytes = None
    date_shift_offset = None
    # Resolve the date-shift secret and compute one deterministic offset for the
    # patient before calling pyDeid. The secret/digest are never stored.
    if stable_date_shift:
        date_shift_secret_bytes = _resolve_date_shift_secret(
            date_shift_secret,
            date_shift_secret_env_var,
        )
        date_shift_offset = _stable_date_shift_offset(
            patient_id=patient_id,
            secret=date_shift_secret_bytes,
            date_shift_days=date_shift_days,
        )

    # Build the explicit patient-alias profile before pyDeid so alias-derived
    # name tokens can improve pyDeid detection. Final stable replacement still
    # only happens later when a pyDeid span matches the alias profile.
    patient_name_alias_profile = None
    patient_name_identity = None
    if stable_patient_name_surrogates:
        patient_name_secret_bytes = _resolve_patient_name_secret(
            patient_name_secret,
            patient_name_secret_env_var,
        )
        patient_name_alias_profile = _build_patient_alias_profile(patient_aliases)
        patient_name_identity = _stable_patient_name_identity(
            patient_id=patient_id,
            secret=patient_name_secret_bytes,
        )
        custom_patient_first_names, custom_patient_last_names = _merge_patient_alias_custom_names(
            patient_name_alias_profile,
            custom_patient_first_names,
            custom_patient_last_names,
        )

    # Custom regexes are converted to pyDeid objects, but pyDeid still performs
    # the actual matching. Protected terms are post-pyDeid span-local vetoes.
    pydeid_custom_regexes, custom_regex_metadata = _build_pydeid_custom_regexes(custom_regexes)
    protected_terms_profile = _build_protected_terms_profile(
        protected_clinical_terms,
        include_builtin_protected_clinical_terms=include_builtin_protected_clinical_terms,
    )

    # Note-level metadata records selected options and safe provenance. It should
    # not include secrets, HMAC digests, raw regex patterns, or raw note text.
    metadata = {
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "note_id": note_id,
        "source": "pyDeid.deid_string",
        "pydeid_types_requested": requested_types,
        "named_entity_recognition": False,
        "stable_date_shift": stable_date_shift,
        "date_shift_days": date_shift_days if stable_date_shift else None,
        "stable_patient_name_surrogates": stable_patient_name_surrogates,
        "custom_regex_rule_ids": [
            item["custom_regex_rule_id"] for item in custom_regex_metadata.values()
        ],
        "include_builtin_protected_clinical_terms": include_builtin_protected_clinical_terms,
        "protected_clinical_term_rule_ids": (
            protected_terms_profile["rule_ids"] if protected_terms_profile is not None else []
        ),
    }

    # pyDeid remains the detector/pruner/initial surrogate source. ProjectPHI
    # passes prepared configuration into pyDeid, then normalizes the returned
    # surrogate records.
    surrogates, deidentified_text = run_pydeid_deid_string(
        note_text,
        pydeid_custom_regexes=pydeid_custom_regexes,
        custom_dr_first_names=custom_dr_first_names,
        custom_dr_last_names=custom_dr_last_names,
        custom_patient_first_names=custom_patient_first_names,
        custom_patient_last_names=custom_patient_last_names,
        named_entity_recognition=False,
        types=metadata["pydeid_types_requested"],
    )

    spans, warnings = normalize_surrogates(
        surrogates,
        patient_id=patient_id,
        encounter_id=encounter_id,
        note_id=note_id,
        custom_regex_metadata=custom_regex_metadata,
    )

    # Reconstruct from original offsets only when ProjectPHI policies may change
    # pyDeid's initial replacements or preserve selected pyDeid spans.
    if stable_date_shift or stable_patient_name_surrogates or protected_terms_profile is not None:
        deidentified_text, spans, reconstruction_warnings = _reconstruct_with_project_replacements(
            note_text,
            spans,
            date_shift_offset=date_shift_offset,
            date_shift_days=date_shift_days,
            patient_name_alias_profile=patient_name_alias_profile,
            patient_name_identity=patient_name_identity,
            protected_terms_profile=protected_terms_profile,
        )
        warnings.extend(reconstruction_warnings)

    return DeidentificationResult(
        original_text=note_text if include_original_text else None,
        deidentified_text=deidentified_text,
        spans=spans,
        warnings=warnings,
        metadata=metadata,
    )
