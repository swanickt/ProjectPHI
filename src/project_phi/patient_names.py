"""Stable patient-name surrogate helpers for explicit pyDeid-detected aliases.

These helpers support deterministic fake patient-name replacement, but only for
names that are explicitly configured as aliases for the current patient.

They do not detect names themselves. pyDeid remains responsible for name
detection and pruning. ProjectPHI only decides whether a pyDeid-detected name
span matches the caller-provided patient alias profile.

Policy summary:
- explicit patient aliases can receive one stable fake identity per patient;
- unknown names keep pyDeid's replacement and are marked as unknown names;
- single-token aliases are handled conservatively to avoid overclaiming an
  unrelated clinician, family member, or other person as the patient;
- titles such as `Mr` / `Mme` are preserved while the family name is replaced.

Examples:
    Given patient aliases `["Jane Smith", "Ms Smith", "Jane"]` and a generated
    fake identity `Alex Bennett`:

    - `Jane Smith` -> `Alex Bennett` with alias_match_type `full`
    - `Jane` -> `Alex` with alias_match_type `given`
    - `Ms Smith` -> `Ms Bennett` with alias_match_type `title_family`
    - `Smith` -> `Bennett` only when policy has enough context to treat it as
      the patient family name
    - an unrelated detected name such as `Dr Brown` -> pyDeid replacement only

- Faker is seeded from a patient/secret HMAC digest for deterministic output;
- the fallback name pools are emergency-only and much smaller than Faker's pool.
"""

from __future__ import annotations

import hashlib
import hmac
import os
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
    patient_name_secret: str | bytes | None,
    patient_name_secret_env_var: str | None,
) -> bytes:
    """Resolve the HMAC secret used for stable patient-name surrogates.

    The secret can be supplied directly or through an environment variable.
    Direct values are useful for tests; environment variables are preferred for
    real runtime configuration.

    Examples:
        Direct string secret:
            _resolve_patient_name_secret("dev-secret", None)

        Direct bytes secret:
            _resolve_patient_name_secret(b"dev-secret", None)

        Environment-backed secret:
            os.environ["PROJECTPHI_PATIENT_NAME_SECRET"] = "runtime-secret"
            _resolve_patient_name_secret(None, "PROJECTPHI_PATIENT_NAME_SECRET")

    Args:
        patient_name_secret: Direct secret value. Strings are encoded as UTF-8.
        patient_name_secret_env_var: Name of the environment variable containing
            the secret. Used only when `patient_name_secret` is not provided.

    Returns:
        Secret bytes suitable for HMAC.

    Raises:
        ValueError: If neither source provides a nonempty secret.

    Notes:
        The secret is never stored in result metadata, span metadata, audit rows,
        warnings, or returned values.
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
    patient_id: str | None,
    secret: bytes,
) -> dict[str, str]:
    """Generate one deterministic fake identity for a patient.

    The identity is derived from `HMAC-SHA256(secret, "patient-name|{patient_id}")`.
    Faker is seeded from the digest so the same `(patient_id, secret)` pair
    produces the same fake name across notes and runs.

    Examples:
        Returned shape:
            {
                "given": "Alex",
                "family": "Bennett",
                "full": "Alex Bennett",
            }

        If the original aliases are `["Jane Smith", "Ms Smith"]`, this identity
        can later be used as:
            - `Jane Smith` -> `Alex Bennett`
            - `Jane` -> `Alex`
            - `Smith` -> `Bennett`
            - `Ms Smith` -> `Ms Bennett`

    Args:
        patient_id: Stable patient key used for deterministic fake identity
            generation.
        secret: HMAC key bytes.

    Returns:
        Dictionary containing `given`, `family`, and `full` fake-name components.

    Raises:
        ValueError: If `patient_id` is empty.

    Notes:
        The raw HMAC digest is never returned. Faker is preferred over the small
        in-source fallback pools.
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
    digest: bytes,
) -> dict[str, str] | None:
    """Generate deterministic Faker name components from an HMAC digest.

    Faker is seeded per instance, not globally, so this helper does not disturb
    Faker use elsewhere in the process. It also intentionally does not infer or
    preserve gender from aliases, notes, diagnoses, or pronouns.

    Args:
        digest: Patient/secret HMAC digest used only as deterministic seed
            material.

    Returns:
        Fake `given`, `family`, and `full` components, or `None` if Faker is
        unavailable or cannot produce usable names.
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
    patient_aliases: Iterable[str] | None,
) -> dict[str, Any]:
    """Normalize explicit patient aliases into conservative matching sets.

    This helper builds the profile used to decide whether a pyDeid-detected name
    span is a known alias for the current patient. It does not infer names from
    note text and does not scan the note.

    Input examples:
        Full alias:
            `Jane Smith`
            - full alias: `jane smith`
            - given name: `jane`
            - family name from full alias: `smith`
            - pyDeid custom first name: `Jane`
            - pyDeid custom last name: `Smith`

        Title-family alias:
            `Ms Smith`
            - title-family alias: `ms smith`
            - title: `ms`
            - explicit family name: `smith`
            - pyDeid custom last name: `Smith`

        Single-token alias:
            `Jane`
            - treated as a given name unless other explicit context makes it a
              known family name
            - added to pyDeid custom first names

    Conservative behavior:
        A single-token alias is treated as a family name only when that family
        name is also supported by a full alias or title-family alias. This avoids
        treating an unrelated clinician/family name as the patient.

    Args:
        patient_aliases: Explicit aliases for one patient. These should come
            from trusted row metadata/configuration, not from automatic note
            inference.

    Returns:
        A profile containing normalized alias sets and pyDeid custom name-list
        tokens.

    Raises:
        ValueError: If no usable aliases are supplied, or if a single-token alias
            is ambiguous between given-name and family-name roles.
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
        # Single-token aliases are intentionally conservative. A token is only
        # treated as a family name when a full alias or title-family alias
        # already establishes that family-name role.
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
    alias_profile: dict[str, Any],
    custom_patient_first_names: set[str] | None,
    custom_patient_last_names: set[str] | None,
) -> tuple[set[str], set[str]]:
    """Merge alias-derived tokens into pyDeid custom patient name lists.

    Alias-derived custom names help pyDeid detect configured patient aliases.
    They do not by themselves trigger ProjectPHI replacement. Stable patient-name
    replacement still happens later only when a pyDeid span matches the explicit
    alias profile.

    Args:
        alias_profile: Profile returned by `_build_patient_alias_profile`.
        custom_patient_first_names: Caller-provided pyDeid patient first-name
            tokens, if any.
        custom_patient_last_names: Caller-provided pyDeid patient last-name
            tokens, if any.

    Returns:
        `(first_names, last_names)` sets to pass to pyDeid.
    """
    first_names = set(custom_patient_first_names or set())
    last_names = set(custom_patient_last_names or set())
    # Alias-derived name lists improve pyDeid detection. Replacement still only
    # happens later when a pyDeid span matches the explicit alias profile.
    first_names.update(alias_profile["custom_first_names"])
    last_names.update(alias_profile["custom_last_names"])
    return first_names, last_names


def _project_patient_name_replacement(
    span: PHISpan,
    *,
    original_text: str,
    alias_profile: dict[str, Any],
    identity: dict[str, str],
) -> tuple[str, str] | None:
    """Return a stable patient-name replacement for a matching pyDeid span.

    Only pyDeid-detected spans that match explicit patient-alias policy receive
    the stable fake identity. Unknown names return `None`, allowing
    reconstruction to keep pyDeid's replacement and mark the span as unknown.

    Examples:
        With alias profile from `["Jane Smith", "Ms Smith", "Jane"]` and fake
        identity `{"given": "Alex", "family": "Bennett", "full": "Alex Bennett"}`:

        - span text `Jane Smith` returns `("Alex Bennett", "full")`
        - span text `Jane` returns `("Alex", "given")`
        - span text `Ms Smith` returns `("Ms Bennett", "title_family")`
        - span text `Smith` may return `("Bennett", "family")` when the span is
          inside a configured full alias in the original note
        - span text `Dr Brown` returns `None`

    Args:
        span: pyDeid-detected name span.
        original_text: Full original note, used only for split-alias context
            checks.
        alias_profile: Explicit patient alias matching profile.
        identity: Deterministic fake patient name components.

    Returns:
        `(replacement, alias_match_type)` for known patient aliases, or `None`
        for unknown names.
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
    original_text: str,
    span: PHISpan,
    full_alias_texts: Iterable[str],
) -> bool:
    """Return whether a split name span falls inside an explicit full alias.

    pyDeid may split a full name into separate given/family spans. This helper
    allows a family-name span to be treated as a patient alias only when its
    original offsets fall within one of the configured full aliases.

    Example:
        Original text:
            `Patient Jane Smith was seen by Dr Smith.`

        If `Jane Smith` is a configured full alias:
            - the `Smith` span inside `Jane Smith` returns True;
            - the `Smith` span inside `Dr Smith` returns False.

    Args:
        original_text: Full original note text.
        span: Split pyDeid name-component span to check.
        full_alias_texts: Normalized full aliases from the patient alias profile.

    Returns:
        True if the span offsets fall inside a configured full alias occurrence.
    """
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
    replacement_source: str,
    policy: str,
) -> dict[str, str]:
    """Return audit metadata for known patient aliases or unknown names.

    Args:
        replacement_source: Source selected for final replacement. The known
            patient-alias path uses `project_stable_patient_name`.
        policy: Alias match type returned by `_project_patient_name_replacement`,
            such as `full`, `given`, `family`, or `title_family`.

    Returns:
        Metadata fields used by audit output:
        - `project_name_policy`
        - `name_role`
        - `alias_match_type`

    Examples:
        Known patient alias:
            {
                "project_name_policy": "known_patient_alias",
                "name_role": "known_patient_alias",
                "alias_match_type": "full",
            }

        Unknown name:
            {
                "project_name_policy": "unknown_name_pydeid",
                "name_role": "unknown_name",
                "alias_match_type": "",
            }
    """
    if replacement_source == "project_stable_patient_name":
        return {
            "project_name_policy": "known_patient_alias",
            "name_role": "known_patient_alias",
            "alias_match_type": policy,
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
    """Normalize alias or span text for conservative matching.

    Normalization:
    - removes periods;
    - casefolds;
    - trims leading/trailing whitespace;
    - collapses repeated whitespace.

    Examples:
        - `"Jane Smith"` -> `"jane smith"`
        - `"Ms. Smith"` -> `"ms smith"`
        - `"  JANE   SMITH  "` -> `"jane smith"`
    """
    return " ".join(str(alias).replace(".", "").casefold().split())


def _alias_token_for_pydeid(
    token: str,  # One normalized alias component.
) -> str:
    """Format one normalized alias token for pyDeid custom name lists.

    Examples:
        - `"jane"` -> `"Jane"`
        - `"smith"` -> `"Smith"`

    This helper assumes the token has already been normalized by
    `_normalize_alias`.
    """
    return token[:1].upper() + token[1:]


def _requested_types_include_names(
    requested_types: Iterable[str],
) -> bool:
    """Return whether caller-requested pyDeid types include name detection.

    Examples:
        - `["names", "dates"]` -> True
        - `["contact", "dates"]` -> False
        - `["Names"]` -> True

    This checks for pyDeid's plural `"names"` category name.
    """
    return any(str(requested_type).lower() == "names" for requested_type in requested_types)
