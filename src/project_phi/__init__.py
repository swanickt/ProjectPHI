"""Public package API for the pyDeid-based ProjectPHI wrapper.

Normal callers should import from this package root instead of private helper
modules. The objects exported here are the supported Python API:

- `PHISpan` and `DeidentificationResult` are structured result containers.
- `deidentify_note(...)` is the single-note de-identification entry point.
- `deidentify_csv(...)` applies the single-note workflow across a CSV.
- `deidentify_patient_notes(...)` applies the single-note workflow across one
  patient timeline with optional patient-local unknown-name surrogates.
- `get_patient_date_shift(...)` returns the patient-specific day offset for
  downstream tabular date shifting.
- config-loader helpers load small CSV/JSON runtime configuration for CLI and
  Python workflows.
"""

from .csv_adapter import deidentify_csv
from .config_loaders import (
    load_patient_alias_manifest,
    load_protected_clinical_terms_csv,
    load_provider_alias_manifest,
)
from .models import DeidentificationResult, PatientDeidentificationResult, PHISpan
from .note import deidentify_note
from .date_shift import get_patient_date_shift
from .patient_batch import deidentify_patient_notes

__all__ = [
    "DeidentificationResult",
    "PatientDeidentificationResult",
    "PHISpan",
    "deidentify_csv",
    "deidentify_note",
    "deidentify_patient_notes",
    "get_patient_date_shift",
    "load_patient_alias_manifest",
    "load_protected_clinical_terms_csv",
    "load_provider_alias_manifest",
]
