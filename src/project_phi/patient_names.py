"""Stable patient-name surrogate helpers for explicit patient aliases.

The policy is intentionally conservative: explicit patient aliases can receive
a stable fake identity, while unknown names remain pyDeid-only replacements.
Alias-derived pyDeid custom name lists are tried first; a bounded exact
residual pass handles supplied aliases that pyDeid pruned before ProjectPHI
could replace them.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from typing import Any, Iterable

from .models import PHISpan


# Emergency fallback only. Normal stable patient-name generation uses Faker
# seeded from the patient HMAC so the surrogate pool is much larger while the
# output remains deterministic for the same patient and secret.
_FAKE_GIVEN_NAMES = [
    "Alex",
    "Avery",
    "Casey",
    "Jamie",
    "Jordan",
    "Morgan",
    "Riley",
    "Taylor",
]

_FAKE_FAMILY_NAMES = [
    "Bennett",
    "Fraser",
    "Laurent",
    "MacLeod",
    "Patel",
    "Sinclair",
    "Tremblay",
    "Walker",
]

_FAKER_LOCALE = "en_CA"

_NAME_TITLES = {"mr", "mrs", "ms", "miss", "mx", "m", "mme", "mlle"}


def _resolve_patient_name_secret(
    patient_name_secret: str | bytes | None,  # Direct secret value for HMAC.
    patient_name_secret_env_var: str | None,  # Env var name containing the secret.
) -> bytes:
    """Resolve the patient-name surrogate secret from value or environment.

    The secret is returned as bytes for HMAC use and is not stored in result
    metadata, span metadata, audit output, or warnings.
    """
    if patient_name_secret is not None:
        if isinstance(patient_name_secret, bytes):
            secret = patient_name_secret
        else:
            secret = patient_name_secret.encode("utf-8")
    elif patient_name_secret_env_var:
        env_secret = os.environ.get(patient_name_secret_env_var)
        secret = env_secret.encode("utf-8") if env_secret else b""
    else:
        secret = b""

    if not secret:
        raise ValueError(
            "stable_patient_name_surrogates=True requires patient_name_secret or a "
            "populated patient_name_secret_env_var."
        )
    return secret


def _stable_patient_name_identity(
    *,
    patient_id: str | None,  # Stable patient key for deterministic fake identity.
    secret: bytes,  # HMAC key bytes.
) -> dict[str, str]:
    """Generate one deterministic fake identity for the patient key.

    Returns a small dictionary with `given`, `family`, and `full` components.
    The raw HMAC digest is never returned. Faker is seeded from the HMAC digest
    so the identity is stable across notes without exposing reversible material.
    Tiny in-source name pools remain only as a fallback if Faker is unavailable
    or cannot produce usable components in the current environment.
    """

    if not patient_id:
        raise ValueError("stable_patient_name_surrogates=True requires a nonempty patient_id.")

    digest = hmac.new(
        secret,
        f"patient-name|{patient_id}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    identity = _stable_patient_name_identity_from_faker(digest)
    if identity is not None:
        return identity

    given = _FAKE_GIVEN_NAMES[int.from_bytes(digest[:8], "big") % len(_FAKE_GIVEN_NAMES)]
    family = _FAKE_FAMILY_NAMES[int.from_bytes(digest[8:16], "big") % len(_FAKE_FAMILY_NAMES)]
    return {"given": given, "family": family, "full": f"{given} {family}"}


def _stable_patient_name_identity_from_faker(
    digest: bytes,  # Patient/secret HMAC digest used only to seed Faker.
) -> dict[str, str] | None:
    """Return deterministic Faker name components, or `None` for fallback pools.

    The Faker dependency is provided transitively by pyDeid in supported
    environments. This helper avoids global Faker seeding and intentionally
    does not infer or preserve gender from aliases, notes, diagnoses, or
    pronouns.
    """

    try:
        from faker import Faker
    except ImportError:
        return None

    seed = int.from_bytes(digest[:16], "big")
    try:
        fake = Faker(_FAKER_LOCALE)
    except Exception:
        fake = Faker()

    try:
        fake.seed_instance(seed)
        given = str(fake.first_name()).strip()
        family = str(fake.last_name()).strip()
    except Exception:
        return None

    if not given or not family:
        return None
    return {"given": given, "family": family, "full": f"{given} {family}"}


def _build_patient_alias_profile(
    patient_aliases: Iterable[str] | None,  # Explicit patient aliases for one patient.
) -> dict[str, Any]:
    """Normalize explicit patient aliases into conservative matching sets.

    This helper does not infer aliases from note text. Full aliases can derive
    given/family components for that patient; title-family aliases preserve the
    title and replace only the family name. Single-token aliases are handled
    cautiously to avoid treating an unrelated clinician/family name as the
    patient.
    """
    aliases = [alias for alias in (patient_aliases or []) if _normalize_alias(alias)]
    if not aliases:
        raise ValueError("stable_patient_name_surrogates=True requires at least one patient alias.")

    profile: dict[str, Any] = {
        "full_aliases": set(),
        "full_alias_texts": [],
        "given_names": set(),
        "family_names_explicit": set(),
        "family_names_from_full": set(),
        "title_family_aliases": {},
        "custom_first_names": set(),
        "custom_last_names": set(),
    }

    single_token_aliases = []
    for alias in aliases:
        normalized = _normalize_alias(alias)
        parts = normalized.split()
        if len(parts) >= 2 and parts[0] not in _NAME_TITLES:
            profile["full_aliases"].add(normalized)
            profile["full_alias_texts"].append(normalized)
            profile["given_names"].add(parts[0])
            profile["family_names_from_full"].add(parts[-1])
            profile["custom_first_names"].add(_alias_token_for_pydeid(parts[0]))
            profile["custom_last_names"].add(_alias_token_for_pydeid(parts[-1]))
        elif len(parts) >= 2 and parts[0] in _NAME_TITLES:
            profile["title_family_aliases"][normalized] = parts[0]
            profile["family_names_explicit"].add(parts[-1])
            profile["custom_last_names"].add(_alias_token_for_pydeid(parts[-1]))
        elif len(parts) == 1:
            single_token_aliases.append(parts[0])

    full_given_names = set(profile["given_names"])
    full_family_names = set(profile["family_names_from_full"])
    title_family_names = set(profile["family_names_explicit"])
    for token in single_token_aliases:
        # Single-token aliases are intentionally conservative: a token is only
        # treated as a family name when explicit full/title-family context exists.
        if token in full_family_names:
            profile["family_names_explicit"].add(token)
            profile["custom_last_names"].add(_alias_token_for_pydeid(token))
        elif token in title_family_names:
            profile["family_names_explicit"].add(token)
            profile["custom_last_names"].add(_alias_token_for_pydeid(token))
        elif token not in full_family_names and token not in title_family_names:
            profile["given_names"].add(token)
            profile["custom_first_names"].add(_alias_token_for_pydeid(token))

    ambiguous_tokens = [
        token
        for token in single_token_aliases
        if token in full_given_names and (token in full_family_names or token in title_family_names)
    ]
    if ambiguous_tokens:
        raise ValueError(
            "stable_patient_name_surrogates=True received an ambiguous single-token patient alias."
        )

    return profile


def _merge_patient_alias_custom_names(
    alias_profile: dict[str, Any],  # Normalized explicit-alias profile.
    custom_patient_first_names: set[str] | None,  # Caller-provided pyDeid first names.
    custom_patient_last_names: set[str] | None,  # Caller-provided pyDeid last names.
) -> tuple[set[str], set[str]]:
    """Merge alias-derived tokens into pyDeid custom patient name lists."""
    first_names = set(custom_patient_first_names or set())
    last_names = set(custom_patient_last_names or set())
    # Alias-derived name lists improve pyDeid detection. Replacement still only
    # happens later when a pyDeid span matches the explicit alias profile.
    first_names.update(alias_profile["custom_first_names"])
    last_names.update(alias_profile["custom_last_names"])
    return first_names, last_names


def _residual_patient_alias_spans(
    original_text: str,  # Full original note text to check for explicit aliases.
    alias_profile: dict[str, Any],  # Normalized explicit-alias profile.
    existing_spans: list[PHISpan],  # pyDeid-emitted spans already selected.
    *,
    patient_id: str | None = None,  # Optional row/note patient identifier for audit metadata.
    encounter_id: str | None = None,  # Optional encounter identifier for audit metadata.
    note_id: str | None = None,  # Optional note identifier for audit metadata.
) -> list[PHISpan]:
    """Return synthetic spans for explicit aliases pyDeid did not emit.

    This is intentionally narrower than a name detector: it checks only aliases
    supplied by the caller for the current patient and uses bounded exact
    matching. It does not infer names or inspect unknown names. Longer aliases
    are considered first so a full alias wins over its given/family components.
    """
    occupied_ranges = [(span.start, span.end) for span in existing_spans]
    residual_spans: list[PHISpan] = []
    candidates = _residual_alias_candidates(alias_profile)

    for normalized_alias in candidates:
        pattern = _residual_alias_pattern(normalized_alias)
        for match in pattern.finditer(original_text):
            span_range = (match.start(), match.end())
            if _range_overlaps_any(span_range, occupied_ranges):
                continue
            text = original_text[match.start() : match.end()]
            residual_spans.append(
                PHISpan(
                    start=match.start(),
                    end=match.end(),
                    text=text,
                    label="NAME",
                    source="ProjectPHI.residual_alias",
                    pydeid_types=["Project residual patient alias"],
                    metadata={
                        "residual_alias": True,
                        "patient_id": patient_id,
                        "encounter_id": encounter_id,
                        "note_id": note_id,
                    },
                )
            )
            occupied_ranges.append(span_range)

    return residual_spans


def _residual_alias_candidates(
    alias_profile: dict[str, Any],  # Normalized explicit-alias profile.
) -> list[str]:
    """Return normalized aliases sorted so longer phrases are matched first."""
    aliases = set()
    aliases.update(alias_profile["full_aliases"])
    aliases.update(alias_profile["title_family_aliases"])
    aliases.update(alias_profile["given_names"])
    aliases.update(alias_profile["family_names_explicit"])
    return sorted(aliases, key=lambda item: (len(item.split()), len(item)), reverse=True)


def _residual_alias_pattern(
    normalized_alias: str,  # Normalized explicit alias.
) -> re.Pattern[str]:
    """Build a bounded exact regex for one normalized alias."""
    parts = normalized_alias.split()
    pattern_parts = []
    for index, part in enumerate(parts):
        escaped = re.escape(part)
        if index == 0 and part in _NAME_TITLES:
            escaped = f"{escaped}\\.?"
        pattern_parts.append(escaped)
    pattern = r"(?<![A-Za-z0-9])" + r"\s+".join(pattern_parts) + r"(?![A-Za-z0-9])"
    return re.compile(pattern, re.IGNORECASE)


def _range_overlaps_any(
    candidate: tuple[int, int],  # Candidate original-note offset range.
    ranges: list[tuple[int, int]],  # Existing occupied original-note ranges.
) -> bool:
    """Return true if `candidate` overlaps any existing span range."""
    start, end = candidate
    return any(start < existing_end and end > existing_start for existing_start, existing_end in ranges)


def _project_patient_name_replacement(
    span: PHISpan,  # pyDeid-detected name span.
    *,
    original_text: str,  # Full original note for split-alias context checks.
    alias_profile: dict[str, Any],  # Explicit patient alias matching profile.
    identity: dict[str, str],  # Deterministic fake patient name components.
) -> tuple[str, str] | None:
    """Return a stable patient-name replacement for a matching pyDeid name span.

    Only pyDeid-detected spans that match explicit alias policy receive the
    stable patient identity. Unknown names return `None` so reconstruction can
    keep pyDeid's replacement and mark the span as an unknown name.
    """
    normalized = _normalize_alias(span.text)
    if not normalized:
        return None
    if normalized in alias_profile["title_family_aliases"]:
        title = span.text.strip().split()[0]
        return f"{title} {identity['family']}", "title_family"
    if normalized in alias_profile["full_aliases"]:
        return identity["full"], "full"
    if normalized in alias_profile["given_names"]:
        return identity["given"], "given"
    if normalized in alias_profile["family_names_explicit"]:
        return identity["family"], "family"
    if (
        normalized in alias_profile["family_names_from_full"]
        and _span_is_inside_full_alias(original_text, span, alias_profile["full_alias_texts"])
    ):
        return identity["family"], "family"
    return None


def _span_is_inside_full_alias(
    original_text: str,  # Full original note text.
    span: PHISpan,  # Split name component span to check.
    full_alias_texts: Iterable[str],  # Explicit full aliases for context.
) -> bool:
    """Return true when a split pyDeid span falls inside an explicit full alias."""
    lowered = original_text.lower()
    for alias_text in full_alias_texts:
        start = lowered.find(alias_text)
        while start != -1:
            end = start + len(alias_text)
            if start <= span.start and span.end <= end:
                return True
            start = lowered.find(alias_text, start + 1)
    return False


def _name_policy_metadata(
    replacement_source: str,  # Source selected for final replacement.
    policy: str,  # Alias match type or unknown-name policy.
) -> dict[str, str]:
    """Return audit metadata for known patient aliases or unknown names."""
    if replacement_source == "project_stable_patient_name":
        return {
            "project_name_policy": "known_patient_alias",
            "name_role": "known_patient_alias",
            "alias_match_type": policy,
        }
    if replacement_source == "project_residual_patient_alias":
        return {
            "project_name_policy": "residual_explicit_patient_alias",
            "name_role": "known_patient_alias",
            "alias_match_type": policy,
        }
    if replacement_source == "project_title_context_action_word_veto":
        return {
            "project_name_policy": "title_context_action_word_veto",
            "name_role": "not_name_action_word",
            "alias_match_type": "",
        }
    # Unknown names may be clinicians, family, or others. They stay pyDeid-only
    # rather than being overclaimed as patient aliases.
    return {
        "project_name_policy": "unknown_name_pydeid",
        "name_role": "unknown_name",
        "alias_match_type": "",
    }


def _normalize_alias(
    alias: str,  # Raw alias or span text to normalize.
) -> str:
    """Casefold, trim, remove periods, and collapse whitespace for alias matching."""
    return " ".join(str(alias).replace(".", "").casefold().split())


def _alias_token_for_pydeid(
    token: str,  # One normalized alias component.
) -> str:
    """Format one alias component for pyDeid custom name-list matching."""
    return token[:1].upper() + token[1:]


def _requested_types_include_names(
    requested_types: Iterable[str],  # Caller-requested pyDeid type names.
) -> bool:
    """Return true when caller-requested pyDeid types include name detection."""
    return any(str(requested_type).lower() == "names" for requested_type in requested_types)
