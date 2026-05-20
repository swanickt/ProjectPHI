"""Single-note ProjectPHI orchestration around pyDeid.

This is the main public workflow. It wires together pyDeid detection/pruning,
span normalization, and optional project-stable replacement.
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
    _residual_patient_alias_spans,
    _resolve_patient_name_secret,
    _stable_patient_name_identity,
)
from .provider_names import (
    _build_provider_alias_profile,
    _merge_provider_alias_custom_names,
    _residual_provider_alias_spans,
    _resolve_provider_name_secret,
    _stable_provider_name_identities,
)
from .protected_terms import _build_protected_terms_profile
from .pydeid_client import DEFAULT_PYDEID_TYPES, run_pydeid_deid_string
from .reconstruction import _reconstruct_with_project_replacements


def deidentify_note(
    note_text: str,  # Original single-note text to send to pyDeid.
    *,
    patient_id: str | None = None,  # Stable patient key and metadata value.
    encounter_id: str | None = None,  # Optional encounter ID for metadata/audit.
    note_id: str | None = None,  # Optional note ID for metadata/audit.
    include_original_text: bool = False,  # Keep original note in the in-memory result.
    types: Iterable[str] | None = None,  # pyDeid PHI categories to request.
    custom_dr_first_names: set[str] | None = None,  # Extra doctor first names for pyDeid.
    custom_dr_last_names: set[str] | None = None,  # Extra doctor last names for pyDeid.
    custom_patient_first_names: set[str] | None = None,  # Extra patient first names for pyDeid.
    custom_patient_last_names: set[str] | None = None,  # Extra patient last names for pyDeid.
    named_entity_recognition: bool = False,  # Must remain False in this baseline.
    stable_date_shift: bool = False,  # Enable project HMAC date replacement.
    date_shift_secret: str | bytes | None = None,  # Direct date-shift secret bytes/text.
    date_shift_secret_env_var: str | None = None,  # Env var containing date-shift secret.
    date_shift_days: int = 45,  # Inclusive +/- date shift range.
    stable_patient_name_surrogates: bool = False,  # Enable explicit-alias patient names.
    patient_aliases: Iterable[str] | None = None,  # Explicit aliases for this patient.
    patient_name_secret: str | bytes | None = None,  # Direct patient-name secret.
    patient_name_secret_env_var: str | None = None,  # Env var containing name secret.
    stable_provider_name_surrogates: bool = False,  # Enable explicit-provider aliases.
    provider_aliases_by_provider_id: dict[str, Iterable[str]] | None = None,  # Provider aliases.
    provider_name_secret: str | bytes | None = None,  # Direct provider-name secret.
    provider_name_secret_env_var: str | None = None,  # Env var containing provider secret.
    custom_regexes=None,  # Project custom regex config to pass through pyDeid.
    protected_clinical_terms=None,  # Runtime protected-term false-positive vetoes.
    include_builtin_protected_clinical_terms: bool = True,  # Include small built-in term set.
) -> DeidentificationResult:
    """De-identify one note with pyDeid detection plus optional project policies.

    `deid_string(...)` remains the detector, pruner, and initial replacement
    source. This function orchestrates project-specific layers around that
    pyDeid result:

    - validates unsupported modes such as NER;
    - resolves requested pyDeid `types`;
    - prepares custom regex and custom name-list inputs for pyDeid;
    - normalizes pyDeid surrogates into `PHISpan` records;
    - adds bounded residual spans for supplied patient aliases that pyDeid
      pruned when stable patient-name surrogates are enabled;
    - adds role-guarded residual spans for supplied provider aliases that pyDeid
      pruned when stable provider-name surrogates are enabled;
    - optionally reconstructs final text from original offsets for stable date
      shifting, stable name aliases, or protected clinical terms.

    ID parameters are copied into result/span metadata for audit context.
    Secrets are used only to derive stable replacements and are not stored in
    the returned result.
    """
    if named_entity_recognition:
        raise ValueError("NER is not enabled in the first project milestone.")
    requested_types = list(types) if types is not None else list(DEFAULT_PYDEID_TYPES)
    if stable_date_shift and not _requested_types_include_dates(requested_types):
        raise ValueError("stable_date_shift=True requires pyDeid date detection in `types`.")
    if (
        stable_patient_name_surrogates or stable_provider_name_surrogates
    ) and not _requested_types_include_names(requested_types):
        raise ValueError(
            "stable name surrogate modes require pyDeid name detection in `types`."
        )

    date_shift_secret_bytes = None
    date_shift_offset = None
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

    provider_name_alias_profile = None
    provider_name_identities = None
    if stable_provider_name_surrogates:
        provider_name_secret_bytes = _resolve_provider_name_secret(
            provider_name_secret,
            provider_name_secret_env_var,
        )
        provider_name_alias_profile = _build_provider_alias_profile(provider_aliases_by_provider_id)
        provider_name_identities = _stable_provider_name_identities(
            provider_name_alias_profile,
            secret=provider_name_secret_bytes,
        )
        custom_dr_first_names, custom_dr_last_names = _merge_provider_alias_custom_names(
            provider_name_alias_profile,
            custom_dr_first_names,
            custom_dr_last_names,
        )

    pydeid_custom_regexes, custom_regex_metadata = _build_pydeid_custom_regexes(custom_regexes)
    protected_terms_profile = _build_protected_terms_profile(
        protected_clinical_terms,
        include_builtin_protected_clinical_terms=include_builtin_protected_clinical_terms,
    )

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
        "stable_provider_name_surrogates": stable_provider_name_surrogates,
        "custom_regex_rule_ids": [
            item["custom_regex_rule_id"] for item in custom_regex_metadata.values()
        ],
        "include_builtin_protected_clinical_terms": include_builtin_protected_clinical_terms,
        "protected_clinical_term_rule_ids": (
            protected_terms_profile["rule_ids"] if protected_terms_profile is not None else []
        ),
    }

    # pyDeid remains the detector/pruner/initial surrogate source. Project code
    # only normalizes spans and optionally reconstructs stable replacements.
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
    if stable_patient_name_surrogates:
        # pyDeid remains the detector for unknown names, but explicit aliases
        # supplied for this patient are allowed a final exact residual pass.
        spans.extend(
            _residual_patient_alias_spans(
                note_text,
                patient_name_alias_profile,
                spans,
                patient_id=patient_id,
                encounter_id=encounter_id,
                note_id=note_id,
            )
        )
    if stable_provider_name_surrogates:
        spans.extend(
            _residual_provider_alias_spans(
                note_text,
                provider_name_alias_profile,
                spans,
                patient_id=patient_id,
                encounter_id=encounter_id,
                note_id=note_id,
            )
        )

    if (
        stable_date_shift
        or stable_patient_name_surrogates
        or stable_provider_name_surrogates
        or protected_terms_profile is not None
    ):
        deidentified_text, spans, reconstruction_warnings = _reconstruct_with_project_replacements(
            note_text,
            spans,
            date_shift_offset=date_shift_offset,
            date_shift_days=date_shift_days,
            patient_name_alias_profile=patient_name_alias_profile,
            patient_name_identity=patient_name_identity,
            provider_name_alias_profile=provider_name_alias_profile,
            provider_name_identities=provider_name_identities,
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
