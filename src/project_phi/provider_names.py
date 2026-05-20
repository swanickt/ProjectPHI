"""Stable provider-name helpers for explicit provider aliases.

Provider aliases are governed runtime configuration, not a detector. The
helpers here can replace exact configured provider names that pyDeid emits or
misses, while unknown names remain pyDeid behavior. Single-token aliases such
as `Chen`, `Green`, or `Cook` require nearby provider-role context so common
ordinary words are not replaced globally.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from typing import Any, Iterable

from .models import PHISpan
from .patient_names import (
    _alias_token_for_pydeid,
    _normalize_alias,
    _range_overlaps_any,
    _stable_patient_name_identity_from_faker,
)

_PROVIDER_ROLE_CONTEXTS = (
    "addiction medicine physician",
    "advanced practice nurse",
    "anesthesiologist",
    "anaesthesiologist",
    "breast radiologist",
    "breast surgeon",
    "cardiologist",
    "clinical pharmacist",
    "clinical psychologist",
    "clinical social worker",
    "dentist",
    "dermatologist",
    "dietitian",
    "doctor",
    "dr",
    "endocrinologist",
    "family doctor",
    "family physician",
    "fellow",
    "gastroenterologist",
    "general practitioner",
    "genetic counsellor",
    "genetic counselor",
    "geriatrician",
    "hematologist",
    "haematologist",
    "infectious disease physician",
    "internist",
    "medical oncologist",
    "midwife",
    "nephrologist",
    "neurologist",
    "nurse",
    "nurse practitioner",
    "occupational therapist",
    "oncologist",
    "ophthalmologist",
    "orthopedic surgeon",
    "orthopaedic surgeon",
    "pathologist",
    "pharmacist",
    "physician",
    "physiotherapist",
    "plastic surgeon",
    "psychiatrist",
    "psychologist",
    "radiation oncologist",
    "radiologist",
    "resident",
    "respirologist",
    "rheumatologist",
    "social worker",
    "surgeon",
)


def _resolve_provider_name_secret(
    provider_name_secret: str | bytes | None,  # Direct provider-name HMAC secret.
    provider_name_secret_env_var: str | None,  # Env var name containing secret.
) -> bytes:
    """Resolve the provider-name surrogate secret without storing it."""
    if provider_name_secret is not None:
        if isinstance(provider_name_secret, bytes):
            secret = provider_name_secret
        else:
            secret = provider_name_secret.encode("utf-8")
    elif provider_name_secret_env_var:
        env_secret = os.environ.get(provider_name_secret_env_var)
        secret = env_secret.encode("utf-8") if env_secret else b""
    else:
        secret = b""

    if not secret:
        raise ValueError(
            "stable_provider_name_surrogates=True requires provider_name_secret or a "
            "populated provider_name_secret_env_var."
        )
    return secret


def _build_provider_alias_profile(
    provider_aliases_by_provider_id: dict[str, Iterable[str]] | None,
) -> dict[str, Any]:
    """Normalize explicit provider aliases into exact matching metadata.

    Provider aliases should be actual names or name components, not role+name
    phrases. Single-token aliases are retained, but they only match when local
    note context looks provider-like.
    """
    if not provider_aliases_by_provider_id:
        raise ValueError(
            "stable_provider_name_surrogates=True requires provider_aliases_by_provider_id."
        )

    aliases: dict[str, dict[str, str]] = {}
    full_alias_texts: dict[str, list[str]] = {}
    custom_first_names: set[str] = set()
    custom_last_names: set[str] = set()

    for provider_id, raw_aliases in provider_aliases_by_provider_id.items():
        provider_key = str(provider_id or "").strip()
        if not provider_key:
            raise ValueError(
                "stable_provider_name_surrogates=True received an empty provider_id."
            )
        provider_aliases = list(raw_aliases or [])
        if not provider_aliases:
            raise ValueError(
                "stable_provider_name_surrogates=True requires aliases for each provider_id."
            )
        for alias in provider_aliases:
            normalized = _normalize_alias(alias)
            if not normalized:
                raise ValueError(
                    "stable_provider_name_surrogates=True received an empty provider alias."
                )
            if normalized in aliases and aliases[normalized]["provider_id"] != provider_key:
                raise ValueError(
                    "stable_provider_name_surrogates=True received duplicate provider aliases."
                )
            parts = normalized.split()
            match_type = "full" if len(parts) >= 2 else "single_token"
            aliases[normalized] = {"provider_id": provider_key, "match_type": match_type}
            if len(parts) >= 2:
                full_alias_texts.setdefault(provider_key, []).append(normalized)
                custom_first_names.add(_alias_token_for_pydeid(parts[0]))
                custom_last_names.add(_alias_token_for_pydeid(parts[-1]))
            else:
                custom_last_names.add(_alias_token_for_pydeid(parts[0]))

    return {
        "aliases": aliases,
        "full_alias_texts": full_alias_texts,
        "custom_first_names": custom_first_names,
        "custom_last_names": custom_last_names,
    }


def _stable_provider_name_identities(
    provider_alias_profile: dict[str, Any],
    *,
    secret: bytes,
) -> dict[str, dict[str, str]]:
    """Generate deterministic fake provider identities keyed by provider_id."""
    provider_ids = {
        alias_info["provider_id"] for alias_info in provider_alias_profile["aliases"].values()
    }
    identities: dict[str, dict[str, str]] = {}
    for provider_id in provider_ids:
        digest = hmac.new(
            secret,
            f"provider-name|{provider_id}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
        identity = _stable_patient_name_identity_from_faker(digest)
        if identity is None:
            from .patient_names import _FAKE_FAMILY_NAMES, _FAKE_GIVEN_NAMES

            given = _FAKE_GIVEN_NAMES[int.from_bytes(digest[:8], "big") % len(_FAKE_GIVEN_NAMES)]
            family = _FAKE_FAMILY_NAMES[
                int.from_bytes(digest[8:16], "big") % len(_FAKE_FAMILY_NAMES)
            ]
            identity = {"given": given, "family": family, "full": f"{given} {family}"}
        identities[provider_id] = identity
    return identities


def _merge_provider_alias_custom_names(
    provider_alias_profile: dict[str, Any],
    custom_dr_first_names: set[str] | None,
    custom_dr_last_names: set[str] | None,
) -> tuple[set[str], set[str]]:
    """Merge provider aliases into pyDeid custom doctor name lists."""
    first_names = set(custom_dr_first_names or set())
    last_names = set(custom_dr_last_names or set())
    first_names.update(provider_alias_profile["custom_first_names"])
    last_names.update(provider_alias_profile["custom_last_names"])
    return first_names, last_names


def _residual_provider_alias_spans(
    original_text: str,
    provider_alias_profile: dict[str, Any],
    existing_spans: list[PHISpan],
    *,
    patient_id: str | None = None,
    encounter_id: str | None = None,
    note_id: str | None = None,
) -> list[PHISpan]:
    """Return synthetic spans for configured provider aliases pyDeid missed."""
    occupied_ranges = [(span.start, span.end) for span in existing_spans]
    residual_spans: list[PHISpan] = []
    candidates = sorted(
        provider_alias_profile["aliases"],
        key=lambda item: (len(item.split()), len(item)),
        reverse=True,
    )

    for normalized_alias in candidates:
        alias_info = provider_alias_profile["aliases"][normalized_alias]
        pattern = _provider_alias_pattern(normalized_alias)
        for match in pattern.finditer(original_text):
            span_range = (match.start(), match.end())
            if _range_overlaps_any(span_range, occupied_ranges):
                continue
            if alias_info["match_type"] == "single_token" and not _has_provider_role_context(
                original_text,
                match.start(),
                match.end(),
            ):
                continue
            residual_spans.append(
                PHISpan(
                    start=match.start(),
                    end=match.end(),
                    text=original_text[match.start() : match.end()],
                    label="NAME",
                    source="ProjectPHI.residual_provider_alias",
                    pydeid_types=["Project residual provider alias"],
                    metadata={
                        "residual_provider_alias": True,
                        "provider_id": alias_info["provider_id"],
                        "provider_alias_match_type": alias_info["match_type"],
                        "patient_id": patient_id,
                        "encounter_id": encounter_id,
                        "note_id": note_id,
                    },
                )
            )
            occupied_ranges.append(span_range)

    return residual_spans


def _project_provider_name_replacement(
    span: PHISpan,
    *,
    original_text: str,
    provider_alias_profile: dict[str, Any],
    provider_name_identities: dict[str, dict[str, str]],
) -> tuple[str, str] | None:
    """Return a stable provider-name replacement for a configured alias span."""
    normalized = _normalize_alias(span.text)
    alias_info = provider_alias_profile["aliases"].get(normalized)
    if alias_info is None:
        alias_info = _component_alias_info_inside_full_alias(
            normalized,
            span,
            original_text,
            provider_alias_profile,
        )
    if alias_info is None:
        return None
    if alias_info["match_type"] == "single_token" and not _has_provider_role_context(
        original_text,
        span.start,
        span.end,
    ):
        return None

    identity = provider_name_identities[alias_info["provider_id"]]
    if alias_info["match_type"] == "full":
        return identity["full"], "full"
    if alias_info["match_type"] == "given":
        return identity["given"], "given"
    return identity["family"], "single_token"


def _component_alias_info_inside_full_alias(
    normalized: str,
    span: PHISpan,
    original_text: str,
    provider_alias_profile: dict[str, Any],
) -> dict[str, str] | None:
    """Support pyDeid split spans when they sit inside configured full aliases."""
    lowered = original_text.casefold()
    for provider_id, full_aliases in provider_alias_profile["full_alias_texts"].items():
        for full_alias in full_aliases:
            parts = full_alias.split()
            if normalized not in {parts[0], parts[-1]}:
                continue
            start = lowered.find(full_alias)
            while start != -1:
                end = start + len(full_alias)
                if start <= span.start and span.end <= end:
                    return {
                        "provider_id": provider_id,
                        "match_type": "given" if normalized == parts[0] else "single_token",
                    }
                start = lowered.find(full_alias, start + 1)
    return None


def _provider_alias_pattern(normalized_alias: str) -> re.Pattern[str]:
    """Build a bounded exact regex for one configured provider alias."""
    return re.compile(
        r"(?<![A-Za-z0-9])" + r"\s+".join(re.escape(part) for part in normalized_alias.split()) + r"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def _has_provider_role_context(
    original_text: str,
    start: int,
    end: int,
) -> bool:
    """Return true when local text around a single token looks provider-like."""
    before = original_text[max(0, start - 64) : start].casefold()
    after = original_text[end : min(len(original_text), end + 32)].casefold()
    before = re.sub(r"[\s.]+$", "", before)
    return any(before.endswith(role) for role in _PROVIDER_ROLE_CONTEXTS) or after.startswith(
        ", md"
    ) or after.startswith(" md")


def _provider_name_policy_metadata(
    replacement_source: str,
    policy: str,
) -> dict[str, str]:
    """Return audit metadata for explicit provider aliases."""
    if replacement_source in {"project_stable_provider_name", "project_residual_provider_alias"}:
        return {
            "project_name_policy": (
                "residual_explicit_provider_alias"
                if replacement_source == "project_residual_provider_alias"
                else "known_provider_alias"
            ),
            "name_role": "known_provider_alias",
            "alias_match_type": policy,
        }
    return {}
