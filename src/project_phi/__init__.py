"""Public package API for the pyDeid-based ProjectPHI wrapper.

Normal callers should import from this package root instead of private helper
modules. The objects exported here are the supported Python API:

- `PHISpan` and `DeidentificationResult` are structured result containers.
- `deidentify_note(...)` is the single-note de-identification entry point.
- `deidentify_csv(...)` applies the single-note workflow across a CSV.
- `load_protected_clinical_terms_csv(...)` loads protected-term CSV config for
  CLI and Python workflows.

Private modules may change more freely; keep `__all__` small and intentional.
"""

from .csv_adapter import deidentify_csv
from .config_loaders import load_protected_clinical_terms_csv
from .models import DeidentificationResult, PHISpan
from .note import deidentify_note

__all__ = [
    "DeidentificationResult",
    "PHISpan",
    "deidentify_csv",
    "deidentify_note",
    "load_protected_clinical_terms_csv",
]