"""Build pyDeid custom regex objects from ProjectPHI config.

ProjectPHI validates the custom regex configuration and records safe provenance
metadata, but it does not run these regexes over note text. pyDeid remains
responsible for matching, pruning, and initial replacement.

The raw regex patterns are deliberately not stored in returned metadata because
they may reveal local identifier formats.
"""

from __future__ import annotations

import re
from typing import Any


def _build_pydeid_custom_regexes(
    custom_regexes,
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    """Validate custom regex config and convert it to pyDeid objects.

    Expected input:
        A dictionary keyed by ProjectPHI rule ID. Each rule config must contain:
        - `phi_type`: nonempty string category passed to pyDeid;
        - `pattern`: nonempty regex pattern string;
        - `replacement`: optional constant replacement string, defaulting to
          `<PHI>`.

    JSON example:
        {
          "synthetic_wb_mrn": {
            "phi_type": "Synthetic WB MRN",
            "pattern": "\\bWB-\\d{7}\\b",
            "replacement": "<SYNTHETIC_MRN>"
          }
        }

    Returns:
        A pair `(pydeid_custom_regexes, metadata_by_phi_type)` where:
        - `pydeid_custom_regexes` can be passed into pyDeid `deid_string(...)`;
        - `metadata_by_phi_type` stores safe rule provenance for normalized
          spans, keyed by configured `phi_type`.

    Patterns are compiled here only to fail fast on invalid regex syntax.
    Matching remains inside pyDeid.
    """
    if custom_regexes is None:
        return {}, {}
    if not isinstance(custom_regexes, dict):
        raise ValueError("custom_regexes must be a dictionary keyed by project rule ID.")

    try:
        from pyDeid.phi_types.utils import create_custom_regex
    except ImportError as exc:
        raise RuntimeError(
            "pyDeid custom regex support is not importable through the local pyDeid package."
        ) from exc

    pydeid_custom_regexes: dict[str, Any] = {}
    metadata_by_phi_type: dict[str, dict[str, str]] = {}
    for rule_id, rule_config in custom_regexes.items():
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError("custom_regexes contains a missing or empty rule ID.")
        sanitized_rule_id = rule_id.strip()
        if not isinstance(rule_config, dict):
            raise ValueError("custom_regexes rule config must be a dictionary.")

        phi_type = rule_config.get("phi_type")
        if not isinstance(phi_type, str) or not phi_type.strip():
            raise ValueError("custom_regexes rule config requires a nonempty phi_type.")
        phi_type = phi_type.strip()
        if phi_type in metadata_by_phi_type:
            raise ValueError("custom_regexes contains duplicate phi_type values.")

        pattern = rule_config.get("pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError("custom_regexes rule config requires a nonempty pattern.")
        try:
            re.compile(pattern)
        except re.error as exc:
            # Patterns may encode local identifier formats, so do not echo them.
            raise ValueError("custom_regexes rule config contains an invalid regex pattern.") from exc

        replacement = rule_config.get("replacement", "<PHI>")
        if not isinstance(replacement, str):
            raise ValueError("custom_regexes rule replacement must be a string.")

        def surrogate_builder(
            replacement_text=replacement,  # Constant replacement for pyDeid custom regex.
        ):
            return replacement_text

        try:
            pydeid_custom_regexes[sanitized_rule_id] = create_custom_regex(
                phi_type,
                pattern,
                surrogate_builder,
                "",
            )
        except Exception as exc:
            raise RuntimeError(
                "pyDeid custom regex support could not be configured through deid_string."
            ) from exc

        metadata_by_phi_type[phi_type] = {
            "custom_regex_rule_id": sanitized_rule_id,
            "custom_regex_phi_type": phi_type,
        }

    return pydeid_custom_regexes, metadata_by_phi_type
