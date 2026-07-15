"""Stable provider-name helpers for explicit provider aliases.

Provider aliases are governed runtime configuration, not a detector. The
helpers here can replace exact configured provider names that pyDeid emits or
misses, while this provider-alias layer leaves unknown names to pyDeid or to
the separate patient batch unknown-name policy. Single-token aliases such
as `Chen`, `Green`, or `Cook` require nearby provider-role context so common
ordinary words are not replaced globally.

The module also handles narrow semantic-preservation cases where pyDeid emits
configured provider aliases beside lower-case clinical verbs. If pyDeid emits
one combined name span, or adjacent provider/action name spans, the alias can
be replaced while the verb is kept when role and following clinical-context
guards pass.
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
from .title_context import (
    _CLINICAL_ACTION_WORDS,
    _following_context_type,
    _normalize_action_word,
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

_AMBIGUOUS_PROVIDER_ALIAS_PREFIX = "__ambiguous_provider_alias__|"


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

    aliases: dict[str, dict[str, Any]] = {}
    full_alias_texts: dict[str, list[str]] = {}
    custom_first_names: set[str] = set()
    custom_last_names: set[str] = set()
    alias_provider_ids: dict[str, set[str]] = {}

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
            parts = normalized.split()
            alias_provider_ids.setdefault(normalized, set()).add(provider_key)
            if len(parts) >= 2:
                custom_first_names.add(_alias_token_for_pydeid(parts[0]))
                custom_last_names.add(_alias_token_for_pydeid(parts[-1]))
            else:
                custom_last_names.add(_alias_token_for_pydeid(parts[0]))

    for normalized, provider_ids in alias_provider_ids.items():
        parts = normalized.split()
        base_match_type = "full" if len(parts) >= 2 else "single_token"
        if len(provider_ids) == 1:
            provider_key = next(iter(provider_ids))
            aliases[normalized] = {
                "provider_id": provider_key,
                "provider_ids": sorted(provider_ids),
                "match_type": base_match_type,
                "ambiguous": False,
            }
        else:
            aliases[normalized] = {
                "provider_id": _ambiguous_provider_alias_identity_key(normalized),
                "provider_ids": sorted(provider_ids),
                "match_type": f"ambiguous_{base_match_type}",
                "ambiguous": True,
            }

        if base_match_type == "full":
            full_alias_texts.setdefault(
                aliases[normalized]["provider_id"],
                [],
            ).append(normalized)

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
                        "provider_id": (
                            ""
                            if alias_info.get("ambiguous")
                            else alias_info["provider_id"]
                        ),
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
    trailing_action_replacement = _project_provider_trailing_action_replacement(
        span,
        original_text=original_text,
        provider_alias_profile=provider_alias_profile,
        provider_name_identities=provider_name_identities,
    )
    if trailing_action_replacement is not None:
        return trailing_action_replacement

    normalized = _normalize_alias(span.text)
    alias_info = provider_alias_profile["aliases"].get(normalized)
    component_alias_info = _component_alias_info_inside_full_alias(
        normalized,
        span,
        original_text,
        provider_alias_profile,
    )
    if component_alias_info is not None and (
        alias_info is None
        or alias_info.get("match_type") == "ambiguous_single_token"
    ):
        alias_info = component_alias_info
    if alias_info is None:
        return None
    if alias_info["match_type"] in {"single_token", "ambiguous_single_token"}:
        if _has_provider_role_context(original_text, span.start, span.end):
            pass
        else:
            alias_info = _component_alias_info_inside_full_alias(
                normalized,
                span,
                original_text,
                provider_alias_profile,
            )
            if alias_info is None or alias_info["match_type"] in {
                "single_token",
                "ambiguous_single_token",
            }:
                return None

    identity = provider_name_identities[alias_info["provider_id"]]
    if alias_info.get("ambiguous"):
        return _provider_alias_replacement_text(alias_info, identity), alias_info["match_type"]
    if alias_info["match_type"] in {"full", "ambiguous_full"}:
        return identity["full"], "full"
    if alias_info["match_type"] in {"given", "ambiguous_given"}:
        return identity["given"], "given"
    if alias_info["match_type"] in {"family", "ambiguous_family"}:
        return identity["family"], "family"
    return identity["family"], "single_token"


def _project_provider_adjacent_action_word_metadata(
    span: PHISpan,
    *,
    original_text: str,
    spans: list[PHISpan],
    provider_alias_profile: dict[str, Any],
    provider_name_identities: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    """Return metadata when a lower-case action follows a provider alias span."""
    if span.label != "NAME":
        return None
    normalized_action = _normalize_action_word(span.text)
    if normalized_action not in _CLINICAL_ACTION_WORDS:
        return None
    if normalized_action in provider_alias_profile["aliases"]:
        return None
    stripped_action = span.text.strip(" \t\r\n.,;:")
    if not stripped_action.isalpha() or not stripped_action.islower():
        return None
    if _following_context_type(span, original_text=original_text) is None:
        return None

    previous_span = _previous_adjacent_span(span, spans, original_text)
    if previous_span is None or previous_span.label != "NAME":
        return None
    provider_replacement = _project_provider_name_replacement(
        previous_span,
        original_text=original_text,
        provider_alias_profile=provider_alias_profile,
        provider_name_identities=provider_name_identities,
    )
    if provider_replacement is None:
        return None
    _replacement_text, previous_policy = provider_replacement
    if previous_policy.endswith("_trailing_action"):
        return None

    return {
        "project_provider_action_policy": (
            "provider_alias_adjacent_lowercase_action_word_match"
        ),
        "project_provider_action_trigger": "explicit_provider_alias_before_action_word",
        "project_provider_action_word": normalized_action,
    }


def _project_provider_trailing_action_replacement(
    span: PHISpan,
    *,
    original_text: str,
    provider_alias_profile: dict[str, Any],
    provider_name_identities: dict[str, dict[str, str]],
) -> tuple[str, str] | None:
    """Preserve a lower-case clinical verb swallowed into a provider-name span.

    This is deliberately narrower than the general title/action veto. It only
    applies when the beginning of the pyDeid name span is an explicit provider
    alias, the alias has provider-role context, and the final token is a
    lower-case clinical action word followed by clinical/generic-patient
    context. Capitalized tokens such as surnames are left to normal provider or
    pyDeid replacement.
    """
    match = re.match(r"^(?P<alias>.+?)(?P<separator>\s+)(?P<action>[A-Za-z]+[.,;:]?)$", span.text)
    if match is None:
        return None

    action_text = match.group("action")
    stripped_action = action_text.strip(".,;:")
    if not stripped_action.isalpha() or not stripped_action.islower():
        return None

    normalized_action = _normalize_action_word(action_text)
    if normalized_action not in _CLINICAL_ACTION_WORDS:
        return None
    if normalized_action in provider_alias_profile["aliases"]:
        return None

    alias_text = match.group("alias")
    normalized_alias = _normalize_alias(alias_text)
    alias_info = provider_alias_profile["aliases"].get(normalized_alias)
    if alias_info is None:
        return None
    if not _has_provider_role_context(
        original_text,
        span.start,
        span.start + match.end("alias"),
    ):
        return None

    action_start = span.start + match.start("action")
    action_span = PHISpan(
        start=action_start,
        end=span.start + match.end("action"),
        text=action_text,
        label=span.label,
        source=span.source,
        pydeid_types=span.pydeid_types,
    )
    if _following_context_type(action_span, original_text=original_text) is None:
        return None

    identity = provider_name_identities[alias_info["provider_id"]]
    replacement_text = _provider_alias_replacement_text(alias_info, identity)
    return (
        f"{replacement_text}{match.group('separator')}{action_text}",
        f"{alias_info['match_type']}_trailing_action",
    )


def _provider_alias_replacement_text(
    alias_info: dict[str, Any],
    identity: dict[str, str],
) -> str:
    """Return the fake provider-name component matching the alias granularity."""
    if alias_info["match_type"] in {"full", "ambiguous_full"}:
        return identity["full"]
    if alias_info["match_type"] in {"given", "ambiguous_given"}:
        return identity["given"]
    return identity["family"]


def _previous_adjacent_span(
    span: PHISpan,
    spans: list[PHISpan],
    original_text: str,
) -> PHISpan | None:
    """Return the immediately preceding span when only whitespace separates it."""
    previous_spans = [candidate for candidate in spans if candidate.end <= span.start]
    if not previous_spans:
        return None
    previous_span = max(previous_spans, key=lambda candidate: (candidate.end, candidate.start))
    between = original_text[previous_span.end : span.start]
    if between.strip():
        return None
    return previous_span


def _component_alias_info_inside_full_alias(
    normalized: str,
    span: PHISpan,
    original_text: str,
    provider_alias_profile: dict[str, Any],
) -> dict[str, Any] | None:
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
                    match_type = "given" if normalized == parts[0] else "family"
                    if _is_ambiguous_provider_alias_identity_key(provider_id):
                        match_type = f"ambiguous_{match_type}"
                    return {
                        "provider_id": provider_id,
                        "provider_ids": [],
                        "match_type": match_type,
                        "ambiguous": _is_ambiguous_provider_alias_identity_key(
                            provider_id
                        ),
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
        if policy.startswith("ambiguous_"):
            return {
                "project_name_policy": "ambiguous_provider_alias",
                "name_role": "known_provider_alias",
                "alias_match_type": policy,
            }
        return {
            "project_name_policy": (
                "residual_explicit_provider_alias"
                if replacement_source == "project_residual_provider_alias"
                else "known_provider_alias"
            ),
            "name_role": "known_provider_alias",
            "alias_match_type": policy,
        }
    if replacement_source == "project_provider_adjacent_action_word_veto":
        return {
            "project_name_policy": "provider_alias_adjacent_action_word_veto",
            "name_role": "not_name_action_word",
            "alias_match_type": policy,
        }
    return {}


def _ambiguous_provider_alias_identity_key(
    normalized_alias: str,
) -> str:
    """Return an internal identity key for duplicate provider aliases."""
    return f"{_AMBIGUOUS_PROVIDER_ALIAS_PREFIX}{normalized_alias}"


def _is_ambiguous_provider_alias_identity_key(
    provider_id: str,
) -> bool:
    """Return true for internal duplicate-alias identity keys."""
    return provider_id.startswith(_AMBIGUOUS_PROVIDER_ALIAS_PREFIX)
