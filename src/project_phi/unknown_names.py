"""Patient-local stable surrogates for pyDeid-detected unknown names.

This module supports the Python batch API. It does not infer new names; it only
builds a per-patient replacement registry from pyDeid `NAME` spans that survived
ProjectPHI's semantic and explicit-alias policies.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from .models import DeidentificationResult, PHISpan
from .patient_names import (
    _NAME_TITLES,
    _normalize_alias,
    _stable_patient_name_identity,
)


_TITLE_REPLACEMENTS = {
    "m": "M.",
    "miss": "Miss",
    "mlle": "Mlle",
    "mme": "Mme",
    "mr": "Mr.",
    "mrs": "Mrs.",
    "ms": "Ms.",
    "mx": "Mx.",
}


@dataclass(frozen=True)
class UnknownNameReplacement:
    """One selected stable replacement for an unknown-name span."""

    text: str
    policy: str


def _resolve_unknown_name_secret(
    unknown_name_secret: str | bytes | None,
    unknown_name_secret_env_var: str | None,
) -> bytes:
    """Resolve the unknown-name surrogate secret from value or environment."""
    if unknown_name_secret is not None:
        if isinstance(unknown_name_secret, bytes):
            secret = unknown_name_secret
        else:
            secret = unknown_name_secret.encode("utf-8")
    elif unknown_name_secret_env_var:
        env_secret = os.environ.get(unknown_name_secret_env_var)
        secret = env_secret.encode("utf-8") if env_secret else b""
    else:
        secret = b""

    if not secret:
        raise ValueError(
            "stable_unknown_name_surrogates=True requires unknown_name_secret or a "
            "populated unknown_name_secret_env_var."
        )
    return secret


def _build_unknown_name_registry(
    results: list[DeidentificationResult],
    *,
    patient_id: str,
    secret: bytes,
) -> dict[str, UnknownNameReplacement]:
    """Build an order-independent patient-local replacement registry."""
    normalized_names: set[str] = set()
    for result in results:
        normalized_names.update(_normalized_unknown_name_span_texts(result))
    full_names = {
        name
        for name in normalized_names
        if _normalized_name_kind(name) in {"full", "title_family"}
    }
    full_identities = {
        name: _unknown_name_identity(patient_id=patient_id, entity_key=name, secret=secret)
        for name in full_names
    }
    component_index = _build_component_index(full_names)

    registry: dict[str, UnknownNameReplacement] = {}
    for name in sorted(normalized_names):
        kind = _normalized_name_kind(name)
        if kind == "full":
            registry[name] = UnknownNameReplacement(
                text=full_identities[name]["full"],
                policy="full",
            )
        elif kind == "title_family":
            registry[name] = UnknownNameReplacement(
                text=_title_family_replacement(name, full_identities[name]),
                policy="title_family",
            )
        elif kind == "single":
            registry[name] = _replacement_for_single_name_component(
                name,
                component_index=component_index,
                full_identities=full_identities,
                patient_id=patient_id,
                secret=secret,
            )
        else:
            registry[name] = UnknownNameReplacement(
                text=_unknown_name_identity(
                    patient_id=patient_id,
                    entity_key=f"phrase|{name}",
                    secret=secret,
                )["full"],
                policy="standalone",
            )
    return registry


def _project_unknown_name_replacement(
    span: PHISpan,
    registry: dict[str, UnknownNameReplacement] | None,
) -> UnknownNameReplacement | None:
    """Return a stable unknown-name replacement for an eligible span."""
    if registry is None or span.label != "NAME":
        return None
    normalized = _normalize_alias(span.text)
    if not normalized:
        return None
    return registry.get(normalized)


def _unknown_name_policy_metadata(
    replacement: UnknownNameReplacement,
) -> dict[str, str]:
    """Return audit metadata for stable unknown-name replacement."""
    return {
        "project_name_policy": "stable_unknown_name_within_patient",
        "name_role": "unknown_name",
        "alias_match_type": replacement.policy,
    }


def _normalized_unknown_name_span_texts(
    result: DeidentificationResult,
) -> set[str]:
    """Return normalized pyDeid fallback name spans from one base result."""
    names: set[str] = set()
    for span in result.spans:
        if not _is_unknown_name_candidate(span):
            continue
        normalized = _normalize_alias(span.text)
        if normalized:
            names.add(normalized)
    return names


def _is_unknown_name_candidate(
    span: PHISpan,
) -> bool:
    """Return true when a base span is still an unknown pyDeid name."""
    if span.label != "NAME" or span.source != "pyDeid":
        return False
    metadata: dict[str, Any] = span.metadata
    if metadata.get("replacement_source") != "pyDeid":
        return False
    project_name_policy = metadata.get("project_name_policy")
    return project_name_policy in {None, "", "unknown_name_pydeid"}


def _normalized_name_kind(
    normalized_name: str,
) -> str:
    """Classify a normalized name-like span for replacement shape."""
    parts = normalized_name.split()
    if len(parts) == 1:
        return "single"
    if parts[0] in _NAME_TITLES:
        return "title_family"
    if len(parts) >= 2:
        return "full"
    return "phrase"


def _build_component_index(
    full_names: set[str],
) -> dict[str, set[tuple[str, str]]]:
    """Map given/family components to full-name records."""
    index: dict[str, set[tuple[str, str]]] = {}
    for full_name in full_names:
        parts = full_name.split()
        if not parts:
            continue
        if parts[0] in _NAME_TITLES:
            core_parts = parts[1:]
            if len(core_parts) == 1:
                _add_component(index, core_parts[0], full_name, "family")
            elif len(core_parts) >= 2:
                _add_component(index, core_parts[0], full_name, "given")
                _add_component(index, core_parts[-1], full_name, "family")
        elif len(parts) >= 2:
            _add_component(index, parts[0], full_name, "given")
            _add_component(index, parts[-1], full_name, "family")
    return index


def _replacement_for_single_name_component(
    normalized_name: str,
    *,
    component_index: dict[str, set[tuple[str, str]]],
    full_identities: dict[str, dict[str, str]],
    patient_id: str,
    secret: bytes,
) -> UnknownNameReplacement:
    """Return linked component replacement when unique, else standalone."""
    matches = component_index.get(normalized_name, set())
    matched_full_names = {full_name for full_name, _role in matches}
    if len(matched_full_names) == 1:
        full_name = next(iter(matched_full_names))
        roles = {role for _full_name, role in matches}
        identity = full_identities[full_name]
        if roles == {"given"}:
            return UnknownNameReplacement(text=identity["given"], policy="linked_given")
        if roles == {"family"}:
            return UnknownNameReplacement(text=identity["family"], policy="linked_family")

    identity = _unknown_name_identity(
        patient_id=patient_id,
        entity_key=f"standalone|{normalized_name}",
        secret=secret,
    )
    return UnknownNameReplacement(text=identity["given"], policy="standalone")


def _title_family_replacement(
    normalized_name: str,
    identity: dict[str, str],
) -> str:
    """Return a title-preserving replacement for title+family spans."""
    title = normalized_name.split()[0]
    return f"{_TITLE_REPLACEMENTS.get(title, title.title())} {identity['family']}"


def _unknown_name_identity(
    *,
    patient_id: str,
    entity_key: str,
    secret: bytes,
) -> dict[str, str]:
    """Generate deterministic fake name components for one unknown entity key."""
    if not patient_id:
        raise ValueError("stable_unknown_name_surrogates=True requires a nonempty patient_id.")
    return _stable_patient_name_identity(
        patient_id=f"unknown-name|{patient_id}|{entity_key}",
        secret=secret,
    )


def _add_component(
    index: dict[str, set[tuple[str, str]]],
    component: str,
    full_name: str,
    role: str,
) -> None:
    """Add one normalized full-name component to the component index."""
    index.setdefault(component, set()).add((full_name, role))
