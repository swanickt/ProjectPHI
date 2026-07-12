from __future__ import annotations

import pytest

from project_phi import deidentify_patient_notes
from project_phi.models import DeidentificationResult, PHISpan


UNKNOWN_SECRET = "timeline-unknown-name-secret"
PATIENT_SECRET = "timeline-patient-name-secret"


def _name_span(note: str, text: str, replacement: str = "Robert") -> PHISpan:
    start = note.index(text)
    return PHISpan(
        start=start,
        end=start + len(text),
        text=text,
        label="NAME",
        source="pyDeid",
        replacement=replacement,
        pydeid_types=["First Name", "Last Name"],
        metadata={"replacement_source": "pyDeid"},
    )


def _fake_deidentify_note_for(mapping):
    def fake_deidentify_note(note_text: str, **kwargs):
        spans = mapping[note_text]
        text = note_text
        for span in sorted(spans, key=lambda item: item.start, reverse=True):
            text = text[: span.start] + (span.replacement or "<PHI>") + text[span.end :]
        return DeidentificationResult(
            original_text=note_text if kwargs.get("include_original_text") else None,
            deidentified_text=text,
            spans=spans,
            warnings=[],
            metadata={
                "patient_id": kwargs.get("patient_id"),
                "encounter_id": kwargs.get("encounter_id"),
                "note_id": kwargs.get("note_id"),
            },
        )

    return fake_deidentify_note


def _stable_unknown_spans(result):
    return [
        span
        for span in result.spans
        if span.metadata.get("replacement_source") == "project_stable_unknown_name"
    ]


def test_patient_batch_links_unique_unknown_name_components(monkeypatch):
    notes = [
        {"note_id": "n1", "note_text": "Maria Lopez called."},
        {"note_id": "n2", "note_text": "Maria called again."},
        {"note_id": "n3", "note_text": "Lopez left a message."},
    ]
    mapping = {
        note["note_text"]: [_name_span(note["note_text"], note["note_text"].split()[0])]
        for note in notes
    }
    mapping["Maria Lopez called."] = [_name_span("Maria Lopez called.", "Maria Lopez")]
    monkeypatch.setattr(
        "project_phi.patient_batch.deidentify_note",
        _fake_deidentify_note_for(mapping),
    )

    batch = deidentify_patient_notes(
        notes,
        patient_id="patient-1",
        stable_unknown_name_surrogates=True,
        unknown_name_secret=UNKNOWN_SECRET,
    )

    full_replacement = _stable_unknown_spans(batch.results[0])[0].replacement
    given_replacement = _stable_unknown_spans(batch.results[1])[0].replacement
    family_replacement = _stable_unknown_spans(batch.results[2])[0].replacement

    assert full_replacement is not None
    full_parts = full_replacement.split()
    assert len(full_parts) == 2
    assert given_replacement == full_parts[0]
    assert family_replacement == full_parts[1]
    assert "Maria" not in batch.results[0].deidentified_text
    assert "Lopez" not in batch.results[2].deidentified_text


def test_patient_batch_keeps_ambiguous_single_token_unknown_names_standalone(monkeypatch):
    notes = [
        {"note_id": "n1", "note_text": "Maria Lopez called."},
        {"note_id": "n2", "note_text": "Maria Santos called."},
        {"note_id": "n3", "note_text": "Maria called again."},
    ]
    mapping = {
        "Maria Lopez called.": [_name_span("Maria Lopez called.", "Maria Lopez")],
        "Maria Santos called.": [_name_span("Maria Santos called.", "Maria Santos")],
        "Maria called again.": [_name_span("Maria called again.", "Maria")],
    }
    monkeypatch.setattr(
        "project_phi.patient_batch.deidentify_note",
        _fake_deidentify_note_for(mapping),
    )

    batch = deidentify_patient_notes(
        notes,
        patient_id="patient-1",
        stable_unknown_name_surrogates=True,
        unknown_name_secret=UNKNOWN_SECRET,
    )

    standalone_span = _stable_unknown_spans(batch.results[2])[0]
    assert standalone_span.metadata["alias_match_type"] == "standalone"
    assert standalone_span.metadata["project_name_policy"] == (
        "stable_unknown_name_within_patient"
    )


def test_patient_batch_unknown_name_replacements_are_order_independent(monkeypatch):
    notes = [
        {"note_id": "n1", "note_text": "Maria Lopez called."},
        {"note_id": "n2", "note_text": "Lopez called again."},
    ]
    mapping = {
        "Maria Lopez called.": [_name_span("Maria Lopez called.", "Maria Lopez")],
        "Lopez called again.": [_name_span("Lopez called again.", "Lopez")],
    }
    monkeypatch.setattr(
        "project_phi.patient_batch.deidentify_note",
        _fake_deidentify_note_for(mapping),
    )

    forward = deidentify_patient_notes(
        notes,
        patient_id="patient-1",
        stable_unknown_name_surrogates=True,
        unknown_name_secret=UNKNOWN_SECRET,
    )
    reverse = deidentify_patient_notes(
        list(reversed(notes)),
        patient_id="patient-1",
        stable_unknown_name_surrogates=True,
        unknown_name_secret=UNKNOWN_SECRET,
    )

    forward_by_id = {result.metadata["note_id"]: result.deidentified_text for result in forward.results}
    reverse_by_id = {result.metadata["note_id"]: result.deidentified_text for result in reverse.results}
    assert forward_by_id == reverse_by_id


def test_patient_batch_unknown_name_replacements_are_patient_local(monkeypatch):
    note = {"note_id": "n1", "note_text": "Maria Lopez called."}
    mapping = {"Maria Lopez called.": [_name_span("Maria Lopez called.", "Maria Lopez")]}
    monkeypatch.setattr(
        "project_phi.patient_batch.deidentify_note",
        _fake_deidentify_note_for(mapping),
    )

    first = deidentify_patient_notes(
        [note],
        patient_id="patient-1",
        stable_unknown_name_surrogates=True,
        unknown_name_secret=UNKNOWN_SECRET,
    )
    second = deidentify_patient_notes(
        [note],
        patient_id="patient-2",
        stable_unknown_name_surrogates=True,
        unknown_name_secret=UNKNOWN_SECRET,
    )

    assert first.results[0].deidentified_text != second.results[0].deidentified_text


def test_patient_batch_known_patient_alias_wins_over_unknown_registry(monkeypatch):
    note = {"note_id": "n1", "note_text": "Maria Lopez called."}
    mapping = {"Maria Lopez called.": [_name_span("Maria Lopez called.", "Maria Lopez")]}
    monkeypatch.setattr(
        "project_phi.patient_batch.deidentify_note",
        _fake_deidentify_note_for(mapping),
    )

    batch = deidentify_patient_notes(
        [note],
        patient_id="patient-1",
        stable_patient_name_surrogates=True,
        patient_aliases=["Maria Lopez"],
        patient_name_secret=PATIENT_SECRET,
        stable_unknown_name_surrogates=True,
        unknown_name_secret=UNKNOWN_SECRET,
    )

    span = batch.results[0].spans[0]
    assert span.metadata["replacement_source"] == "project_stable_patient_name"
    assert span.metadata["project_name_policy"] == "known_patient_alias"


def test_patient_batch_known_patient_alias_accepts_name_style(monkeypatch):
    note = {"note_id": "n1", "note_text": "Maria Lopez called."}
    mapping = {"Maria Lopez called.": [_name_span("Maria Lopez called.", "Maria Lopez")]}
    monkeypatch.setattr(
        "project_phi.patient_batch.deidentify_note",
        _fake_deidentify_note_for(mapping),
    )

    batch = deidentify_patient_notes(
        [note],
        patient_id="patient-1",
        stable_patient_name_surrogates=True,
        patient_aliases=["Maria Lopez"],
        patient_name_style="feminine",
        patient_name_secret=PATIENT_SECRET,
        stable_unknown_name_surrogates=True,
        unknown_name_secret=UNKNOWN_SECRET,
    )

    span = batch.results[0].spans[0]
    assert span.metadata["replacement_source"] == "project_stable_patient_name"
    assert span.metadata["patient_name_style"] == "feminine"


def test_patient_batch_semantic_veto_wins_over_unknown_registry(monkeypatch):
    note = {"note_id": "n1", "note_text": "Hamilton Depression Scale was elevated."}
    mapping = {
        note["note_text"]: [_name_span(note["note_text"], "Hamilton", replacement="Robert")]
    }
    monkeypatch.setattr(
        "project_phi.patient_batch.deidentify_note",
        _fake_deidentify_note_for(mapping),
    )

    batch = deidentify_patient_notes(
        [note],
        patient_id="patient-1",
        stable_unknown_name_surrogates=True,
        unknown_name_secret=UNKNOWN_SECRET,
    )

    span = batch.results[0].spans[0]
    assert span.replacement == "Hamilton"
    assert span.metadata["replacement_source"] == "project_protected_clinical_term"


def test_patient_batch_without_unknown_mode_keeps_base_pydeid_behavior(monkeypatch):
    note = {"note_id": "n1", "note_text": "Maria Lopez called."}
    mapping = {"Maria Lopez called.": [_name_span("Maria Lopez called.", "Maria Lopez")]}
    monkeypatch.setattr(
        "project_phi.patient_batch.deidentify_note",
        _fake_deidentify_note_for(mapping),
    )

    batch = deidentify_patient_notes([note], patient_id="patient-1")

    assert batch.results[0].original_text is None
    assert batch.results[0].deidentified_text == "Robert called."
    assert batch.metadata["stable_unknown_name_surrogates"] is False


def test_patient_batch_unknown_mode_requires_name_detection_when_types_supplied():
    with pytest.raises(ValueError, match="requires pyDeid name detection"):
        deidentify_patient_notes(
            ["Maria Lopez called."],
            patient_id="patient-1",
            types=["dates"],
            stable_unknown_name_surrogates=True,
            unknown_name_secret=UNKNOWN_SECRET,
        )
