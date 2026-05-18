"""Title-context action-word veto tests using synthetic examples only.

These tests cover ProjectPHI's title-context action-word veto.

The policy protects common lowercase clinical action words that pyDeid may
mistakenly classify as names after a title-like token such as `Dr.`. The veto is
span-local and conservative: it preserves only supported lowercase action words
in strict title context, while leaving real names, capitalized tokens, custom
name-list matches, and known patient aliases to their normal replacement
policies.

Main contracts covered:
- lowercase action words after title context can be preserved;
- normal title-name spans are still replaced by pyDeid;
- capitalized action-looking tokens are not preserved;
- action words outside title context are not preserved;
- explicit patient aliases take priority over the title-context veto;
- custom pyDeid name-list spans and pyDeid name-list guards block the veto;
- the public note and CSV workflows record title-context metadata safely.

All examples are synthetic.
"""

from project_phi import PHISpan, deidentify_csv, deidentify_note
import project_phi.reconstruction as reconstruction
import project_phi.title_context as title_context
from project_phi.patient_names import _build_patient_alias_profile
from conftest import _read_csv, _write_csv


def _name_span(text, start, *, replacement="Carter", pydeid_types=None):
    """Build a synthetic pyDeid-like name span for reconstruction tests.

    The default span pretends pyDeid detected `text` as a name and assigned the
    replacement `"Carter"`. Tests then check whether reconstruction preserves the
    span through title-context policy or falls back to the pyDeid replacement.

    Example:
        `_name_span("examined", 8)` creates a span with:
        - original text `"examined"`;
        - original-note offsets `8:16`;
        - label `"NAME"`;
        - pyDeid replacement `"Carter"`.
    """
    return PHISpan(
        start=start,
        end=start + len(text),
        text=text,
        label="NAME",
        source="pyDeid",
        replacement=replacement,
        pydeid_types=pydeid_types or ["Last Name (STitle)"],
        metadata={
            "pydeid_replacement": replacement,
            "pydeid_surrogate_start": start,
            "pydeid_surrogate_end": start + len(replacement),
        },
    )


# Direct reconstruction behavior.


def test_reconstruction_preserves_lowercase_action_word_after_title():
    """A lowercase action word in strict title context is preserved."""
    note = "The Dr. examined the patient."
    span = _name_span("examined", 8)

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == note
    assert warnings == []
    assert spans[0].action == "preserved"
    assert spans[0].replacement == "examined"
    assert spans[0].metadata["replacement_source"] == "project_title_context_action_word_veto"
    assert spans[0].metadata["project_title_context_policy"] == (
        "title_context_action_word_exact_match"
    )
    assert spans[0].metadata["project_title_context_word"] == "examined"
    start = spans[0].metadata["project_replacement_start"]
    end = spans[0].metadata["project_replacement_end"]
    assert text[start:end] == "examined"
    assert note[spans[0].start : spans[0].end] == "examined"


def test_reconstruction_preserves_action_word_after_single_title_name_span():
    """A normal title-name span can be replaced while the following action word is preserved."""
    note = "Dr. Solen reviewed mammography."
    spans = [
        _name_span("Solen", 4, replacement="Bennett"),
        _name_span("reviewed", 10, replacement="Avery", pydeid_types=["Name (STitle)"]),
    ]

    text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert warnings == []
    assert text == "Dr. Bennett reviewed mammography."
    assert final_spans[0].metadata["replacement_source"] == "pyDeid"
    assert final_spans[1].metadata["replacement_source"] == "project_title_context_action_word_veto"
    assert final_spans[1].action == "preserved"


def test_reconstruction_does_not_preserve_capitalized_action_word_after_title():
    """Capitalized title-context tokens are treated as names and use pyDeid replacement."""
    note = "Dr. Examined the patient."
    span = _name_span("Examined", 4)

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == "Dr. Carter the patient."
    assert spans[0].action == "replaced"
    assert spans[0].metadata["replacement_source"] == "pyDeid"
    assert "project_title_context_policy" not in spans[0].metadata


def test_reconstruction_does_not_preserve_action_word_without_title_context():
    """Action-looking words outside title context are not preserved by this veto."""
    note = "The note reviewed mammography."
    span = _name_span("reviewed", 9, replacement="Avery", pydeid_types=["Name (STitle)"])

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == "The note Avery mammography."
    assert spans[0].metadata["replacement_source"] == "pyDeid"


# Priority/guard behavior.


def test_reconstruction_patient_alias_wins_over_action_word_veto():
    """Explicit patient aliases take priority over the title-context action-word veto."""
    note = "Dr. reviewed the patient."
    span = _name_span("reviewed", 4)
    alias_profile = _build_patient_alias_profile(["reviewed"])
    identity = {"given": "Morgan", "family": "Walker", "full": "Morgan Walker"}

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        [span],
        patient_name_alias_profile=alias_profile,
        patient_name_identity=identity,
    )

    assert text == "Dr. Morgan the patient."
    assert spans[0].metadata["replacement_source"] == "project_stable_patient_name"
    assert spans[0].metadata["project_name_policy"] == "known_patient_alias"


def test_reconstruction_custom_name_list_span_blocks_action_word_veto():
    """Custom pyDeid name-list matches are not overridden by title-context preservation."""
    note = "Dr. reviewed the patient."
    span = _name_span(
        "reviewed",
        4,
        pydeid_types=["Custom Doctor Last Name", "Last Name (STitle)"],
    )

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == "Dr. Carter the patient."
    assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_pydeid_name_list_guard_blocks_action_word_veto(monkeypatch):
    """Words present in pyDeid's name lists are guarded from action-word preservation."""
    note = "Dr. reviewed the patient."
    span = _name_span("reviewed", 4)

    monkeypatch.setattr(title_context, "_load_pydeid_name_words", lambda: frozenset({"reviewed"}))

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == "Dr. Carter the patient."
    assert spans[0].metadata["replacement_source"] == "pyDeid"


# Public note workflow behavior.


def test_deidentify_note_preserves_title_context_action_words_from_pydeid():
    """The public note workflow preserves pyDeid-emitted title-context action words."""
    note = "The Dr. examined the patient. Dr. Solen reviewed mammography."

    result = deidentify_note(note)

    assert "The Dr. examined the patient." in result.deidentified_text
    assert "reviewed mammography" in result.deidentified_text
    assert "Solen" not in result.deidentified_text
    preserved_words = [
        span.text
        for span in result.spans
        if span.metadata.get("replacement_source") == "project_title_context_action_word_veto"
    ]
    assert {"examined", "reviewed"}.issubset(set(preserved_words))


def test_deidentify_note_preserves_protected_term_plus_following_action_word():
    """Protected-term preservation can coexist with a following title-context action word."""
    note = "Dr. Tomosynthesis reviewed mammography with tomosynthesis."

    result = deidentify_note(note)

    assert result.deidentified_text == note
    assert any(
        span.metadata.get("replacement_source") == "project_protected_clinical_term"
        and span.text == "Tomosynthesis"
        for span in result.spans
    )
    assert any(
        span.metadata.get("replacement_source") == "project_title_context_action_word_veto"
        and span.text == "reviewed"
        for span in result.spans
    )


def test_deidentify_note_keeps_capitalized_title_token_as_pydeid_replacement():
    """The public workflow does not preserve capitalized action-looking name spans."""
    note = "Dr. Examined the patient."

    result = deidentify_note(note)

    assert "Examined" not in result.deidentified_text
    assert not any(
        span.metadata.get("replacement_source") == "project_title_context_action_word_veto"
        for span in result.spans
    )


# CSV/audit behavior.


def test_deidentify_csv_audit_records_title_context_metadata(tmp_path):
    """CSV audit output records title-context policy metadata without changing the note."""
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-title-001",
                "note_id": "Note/synth-title-001",
                "note_text": "The Dr. examined the patient.",
            }
        ],
    )

    summary = deidentify_csv(input_file, output_file, audit_output_file=audit_file)

    output_rows = _read_csv(output_file)
    audit_rows = _read_csv(audit_file)
    title_rows = [
        row
        for row in audit_rows
        if row["replacement_source"] == "project_title_context_action_word_veto"
    ]
    assert summary["rows_failed"] == 0
    assert output_rows[0]["note_text"] == "The Dr. examined the patient."
    assert title_rows
    assert title_rows[0]["project_title_context_policy"] == (
        "title_context_action_word_exact_match"
    )
    assert title_rows[0]["project_title_context_trigger"] == "strict_title_name_heuristic"
    assert title_rows[0]["project_title_context_word"] == "examined"