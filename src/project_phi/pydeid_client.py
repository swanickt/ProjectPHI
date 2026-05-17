"""Small wrapper around pyDeid's `deid_string(...)` API.

This module keeps direct pyDeid calls in one place. The rest of ProjectPHI should
call `run_pydeid_deid_string(...)` instead of importing pyDeid directly.

Responsibilities here:
- define the default pyDeid PHI categories used by ProjectPHI;
- lazily import pyDeid so non-de-identification code can still be imported
  before pyDeid is installed;
- merge ProjectPHI's prepared custom regex objects into the pyDeid call;
- suppress pyDeid stdout when custom regexes are used.

This module does not normalize pyDeid output into ProjectPHI span records.
`normalization.py` handles that step.
"""

from __future__ import annotations

import contextlib
import io


DEFAULT_PYDEID_TYPES = [
    "names",
    "dates",
    "sin",
    "ohip",
    "mrn",
    "locations",
    "hospitals",
    "contact",
]
"""pyDeid PHI categories used when the caller does not pass an explicit `types` list."""


def run_pydeid_deid_string(
    note_text: str,
    *,
    pydeid_custom_regexes: dict,
    **kwargs,
):
    """Run pyDeid on one note using ProjectPHI-prepared options.

    `note_text` is passed to pyDeid unchanged. `pydeid_custom_regexes` should
    already be validated and converted into the keyword arguments expected by
    pyDeid. Additional `kwargs` are forwarded directly to `deid_string(...)`.

    Returns pyDeid's raw `(surrogates, deidentified_text)` tuple. Callers are
    responsible for normalizing the result into ProjectPHI objects.
    """
    deid_string = _load_deid_string()
    deid_kwargs = {**kwargs, **pydeid_custom_regexes}

    if pydeid_custom_regexes:
        # pyDeid prints custom regex objects to stdout, including raw patterns.
        # Suppress that output so configured identifier formats do not appear in
        # CLI output, logs, notebooks, or test output.
        with contextlib.redirect_stdout(io.StringIO()):
            return deid_string(note_text, **deid_kwargs)

    return deid_string(note_text, **deid_kwargs)


def _load_deid_string():
    """Import pyDeid only when de-identification is actually used."""
    try:
        from pyDeid import deid_string
    except ImportError as exc:
        raise RuntimeError(
            "pyDeid is not importable. Please install pyDeid from the pinned project dependency."
        ) from exc

    return deid_string