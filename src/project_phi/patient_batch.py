"""Per-patient Python batch de-identification helpers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from .date_shift import get_patient_date_shift
from .models import DeidentificationResult, PatientDeidentificationResult
from .note import deidentify_note
from .patient_names import (
    _build_patient_alias_profile,
    _requested_types_include_names,
    _resolve_patient_name_secret,
    _stable_patient_name_identity,
)
from .provider_names import (
    _build_provider_alias_profile,
    _resolve_provider_name_secret,
    _stable_provider_name_identities,
)
from .protected_terms import _build_protected_terms_profile
from .reconstruction import _reconstruct_with_project_replacements
from .unknown_names import _build_unknown_name_registry, _resolve_unknown_name_secret


def deidentify_patient_notes(
    notes: Iterable[str | dict[str, Any]],
    *,
    patient_id: str,
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
    shift_partial_month_day_dates: bool = True,
    stable_patient_name_surrogates: bool = False,
    patient_aliases: Iterable[str] | None = None,
    patient_name_secret: str | bytes | None = None,
    patient_name_secret_env_var: str | None = None,
    stable_provider_name_surrogates: bool = False,
    provider_aliases_by_provider_id: dict[str, Iterable[str]] | None = None,
    provider_name_secret: str | bytes | None = None,
    provider_name_secret_env_var: str | None = None,
    stable_unknown_name_surrogates: bool = False,
    unknown_name_secret: str | bytes | None = None,
    unknown_name_secret_env_var: str | None = None,
    custom_regexes=None,
    protected_clinical_terms=None,
    include_builtin_protected_clinical_terms: bool = True,
) -> PatientDeidentificationResult:
    """De-identify one patient's notes with optional timeline-stable names.

    This API preserves existing single-note behavior by calling
    `deidentify_note(...)` for the base pyDeid pass. When
    `stable_unknown_name_surrogates=True`, it builds a patient-local registry
    from remaining pyDeid `NAME` spans across the supplied notes and reconstructs
    those spans consistently within this batch.

    `notes` may contain raw strings or dictionaries with `note_text` plus
    optional `note_id` and `encounter_id`. If a dictionary includes
    `patient_id`, it must match the function-level `patient_id`.
    """
    if not patient_id:
        raise ValueError("deidentify_patient_notes(...) requires a nonempty patient_id.")

    requested_types = list(types) if types is not None else None
    if stable_unknown_name_surrogates and requested_types is not None:
        if not _requested_types_include_names(requested_types):
            raise ValueError(
                "stable_unknown_name_surrogates=True requires pyDeid name detection "
                "in `types`."
            )

    note_records = _normalize_patient_note_records(notes, patient_id=patient_id)
    base_results = [
        deidentify_note(
            record["note_text"],
            patient_id=patient_id,
            encounter_id=record.get("encounter_id"),
            note_id=record.get("note_id"),
            include_original_text=True,
            types=requested_types,
            custom_dr_first_names=custom_dr_first_names,
            custom_dr_last_names=custom_dr_last_names,
            custom_patient_first_names=custom_patient_first_names,
            custom_patient_last_names=custom_patient_last_names,
            named_entity_recognition=named_entity_recognition,
            stable_date_shift=stable_date_shift,
            date_shift_secret=date_shift_secret,
            date_shift_secret_env_var=date_shift_secret_env_var,
            date_shift_days=date_shift_days,
            shift_partial_month_day_dates=shift_partial_month_day_dates,
            stable_patient_name_surrogates=stable_patient_name_surrogates,
            patient_aliases=patient_aliases,
            patient_name_secret=patient_name_secret,
            patient_name_secret_env_var=patient_name_secret_env_var,
            stable_provider_name_surrogates=stable_provider_name_surrogates,
            provider_aliases_by_provider_id=provider_aliases_by_provider_id,
            provider_name_secret=provider_name_secret,
            provider_name_secret_env_var=provider_name_secret_env_var,
            custom_regexes=custom_regexes,
            protected_clinical_terms=protected_clinical_terms,
            include_builtin_protected_clinical_terms=include_builtin_protected_clinical_terms,
        )
        for record in note_records
    ]

    date_shift_offset = None
    if stable_date_shift:
        date_shift_offset = get_patient_date_shift(
            patient_id=patient_id,
            date_shift_secret=date_shift_secret,
            date_shift_secret_env_var=date_shift_secret_env_var,
            date_shift_days=date_shift_days,
        )

    if not stable_unknown_name_surrogates:
        return PatientDeidentificationResult(
            patient_id=patient_id,
            results=[
                _strip_original_text(result, include_original_text=include_original_text)
                for result in base_results
            ],
            date_shift_offset_days=date_shift_offset,
            warnings=_dedupe_warnings(base_results),
            metadata={
                "stable_unknown_name_surrogates": False,
                "note_count": len(base_results),
            },
        )

    unknown_name_secret_bytes = _resolve_unknown_name_secret(
        unknown_name_secret,
        unknown_name_secret_env_var,
    )
    unknown_name_registry = _build_unknown_name_registry(
        base_results,
        patient_id=patient_id,
        secret=unknown_name_secret_bytes,
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

    protected_terms_profile = _build_protected_terms_profile(
        protected_clinical_terms,
        include_builtin_protected_clinical_terms=include_builtin_protected_clinical_terms,
    )

    final_results = [
        _reconstruct_patient_batch_result(
            result,
            include_original_text=include_original_text,
            date_shift_offset=date_shift_offset,
            date_shift_days=date_shift_days,
            patient_name_alias_profile=patient_name_alias_profile,
            patient_name_identity=patient_name_identity,
            provider_name_alias_profile=provider_name_alias_profile,
            provider_name_identities=provider_name_identities,
            protected_terms_profile=protected_terms_profile,
            shift_partial_month_day_dates=shift_partial_month_day_dates,
            unknown_name_registry=unknown_name_registry,
        )
        for result in base_results
    ]

    return PatientDeidentificationResult(
        patient_id=patient_id,
        results=final_results,
        date_shift_offset_days=date_shift_offset,
        warnings=_dedupe_warnings(final_results),
        metadata={
            "stable_unknown_name_surrogates": True,
            "stable_unknown_name_count": len(unknown_name_registry),
            "note_count": len(final_results),
        },
    )


def _normalize_patient_note_records(
    notes: Iterable[str | dict[str, Any]],
    *,
    patient_id: str,
) -> list[dict[str, Any]]:
    """Normalize raw strings or note dictionaries into internal records."""
    records: list[dict[str, Any]] = []
    for index, note in enumerate(notes):
        if isinstance(note, str):
            records.append(
                {
                    "note_text": note,
                    "note_id": None,
                    "encounter_id": None,
                }
            )
            continue
        if not isinstance(note, dict):
            raise TypeError("notes must contain strings or dictionaries.")

        record_patient_id = note.get("patient_id")
        if record_patient_id is not None and str(record_patient_id) != str(patient_id):
            raise ValueError("note patient_id does not match batch patient_id.")

        records.append(
            {
                "note_text": "" if note.get("note_text") is None else str(note.get("note_text")),
                "note_id": note.get("note_id", f"note-{index}"),
                "encounter_id": note.get("encounter_id"),
            }
        )
    return records


def _reconstruct_patient_batch_result(
    result: DeidentificationResult,
    *,
    include_original_text: bool,
    date_shift_offset: int | None,
    date_shift_days: int,
    patient_name_alias_profile: dict[str, Any] | None,
    patient_name_identity: dict[str, str] | None,
    provider_name_alias_profile: dict[str, Any] | None,
    provider_name_identities: dict[str, dict[str, str]] | None,
    protected_terms_profile: dict[str, Any] | None,
    shift_partial_month_day_dates: bool,
    unknown_name_registry: dict[str, Any],
) -> DeidentificationResult:
    """Reconstruct one base result with the patient-local unknown registry."""
    original_text = result.original_text or ""
    deidentified_text, spans, reconstruction_warnings = _reconstruct_with_project_replacements(
        original_text,
        result.spans,
        date_shift_offset=date_shift_offset,
        date_shift_days=date_shift_days,
        patient_name_alias_profile=patient_name_alias_profile,
        patient_name_identity=patient_name_identity,
        provider_name_alias_profile=provider_name_alias_profile,
        provider_name_identities=provider_name_identities,
        protected_terms_profile=protected_terms_profile,
        shift_partial_month_day_dates=shift_partial_month_day_dates,
        unknown_name_registry=unknown_name_registry,
    )
    metadata = dict(result.metadata)
    metadata["stable_unknown_name_surrogates"] = True
    return replace(
        result,
        original_text=original_text if include_original_text else None,
        deidentified_text=deidentified_text,
        spans=spans,
        warnings=_dedupe_warning_values([*result.warnings, *reconstruction_warnings]),
        metadata=metadata,
    )


def _strip_original_text(
    result: DeidentificationResult,
    *,
    include_original_text: bool,
) -> DeidentificationResult:
    """Return a result copy with original text retained only when requested."""
    if include_original_text:
        return result
    return replace(result, original_text=None)


def _dedupe_warnings(
    results: list[DeidentificationResult],
) -> list[str]:
    """Return sanitized batch-level warnings without duplicates."""
    return _dedupe_warning_values(
        warning for result in results for warning in result.warnings
    )


def _dedupe_warning_values(
    warnings: Iterable[str],
) -> list[str]:
    """Return warnings in first-seen order without duplicates."""
    deduped: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        deduped.append(warning)
    return deduped
