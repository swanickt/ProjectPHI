"""Title-context action-word veto tests using synthetic examples only."""

from project_phi import PHISpan, deidentify_csv, deidentify_note
import project_phi.reconstruction as reconstruction
import project_phi.title_context as title_context
from project_phi.patient_names import _build_patient_alias_profile
from conftest import _read_csv, _write_csv


def _name_span(text, start, *, replacement="Carter", pydeid_types=None):
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


def test_reconstruction_preserves_lowercase_action_word_after_title():
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


def test_reconstruction_preserves_article_name_false_positive():
    note = "The patient comes to the physician for a 3-month history of fatigue."
    span = _name_span("a", note.index("a 3-month"), replacement="Maxwell", pydeid_types=["Name Initial (PRE)"])

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == note
    assert warnings == []
    assert spans[0].action == "preserved"
    assert spans[0].metadata["replacement_source"] == "project_ordinary_token_veto"
    assert spans[0].metadata["project_ordinary_token_policy"] == "preserved_pronoun_or_article"
    assert spans[0].metadata["project_ordinary_token"] == "a"
    assert spans[0].metadata["project_ordinary_token_category"] == "pronoun_or_article"


def test_reconstruction_preserves_pronoun_name_false_positives():
    examples = [
        ("He currently uses inhaled corticosteroid.", "He"),
        ("Her family history is negative.", "Her"),
        ("An rRT-PCR for synthetic virus was negative.", "An"),
    ]

    for note, token in examples:
        span = _name_span(token, note.index(token), replacement="Carter", pydeid_types=["Name (NI)"])

        text, spans, warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

        assert text == note
        assert warnings == []
        assert spans[0].metadata["replacement_source"] == "project_ordinary_token_veto"


def test_reconstruction_preserves_pronoun_after_uppercase_clinical_abbreviation():
    examples = [
        ("Noted to have mild MR. He was sent home.", "He"),
        ("Noted to have mild MR. Her family called.", "Her"),
    ]

    for note, token in examples:
        span = _name_span(token, note.index(token), replacement="Carter", pydeid_types=["Name (NI)"])

        text, spans, warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

        assert text == note
        assert warnings == []
        assert spans[0].metadata["replacement_source"] == "project_ordinary_token_veto"


def test_reconstruction_preserves_nh_only_in_nursing_home_context():
    note = "A 87 year old female NH resident presented with abdominal pain."
    span = _name_span("NH", note.index("NH"), replacement="Donna", pydeid_types=["Name8 (MD)"])

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == note
    assert warnings == []
    assert spans[0].metadata["replacement_source"] == "project_ordinary_token_veto"
    assert spans[0].metadata["project_ordinary_token_policy"] == "preserved_clinical_shorthand"
    assert spans[0].metadata["project_ordinary_token_category"] == "nursing_home"


def test_reconstruction_does_not_preserve_article_in_initial_contexts():
    examples = [
        ("A. Smith reviewed the note.", "A"),
        ("Dr. A reviewed the note.", "A"),
        ("Patient A enrolled.", "A"),
        ("Subject A reported symptoms.", "A"),
        ("Case A was excluded.", "A"),
        ("Mr. A called.", "A"),
        ("Ms. A called.", "A"),
        ("Dr. A reviewed the note.", "A"),
        ("Mr. He was sent home.", "He"),
    ]

    for note, token in examples:
        span = _name_span(token, note.index(token), replacement="Carter", pydeid_types=["Name Initial (PRE)"])

        text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

        assert text != note
        assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_does_not_preserve_nh_without_nursing_home_context():
    note = "Synthetic NH marker was recorded."
    span = _name_span("NH", note.index("NH"), replacement="Donna", pydeid_types=["Name8 (MD)"])

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == "Synthetic Donna marker was recorded."
    assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_preserves_action_word_after_single_title_name_span():
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


def test_reconstruction_preserves_split_dr_title_after_clinical_role():
    note = "Copy of note to family physician Dr. Michael Tan."
    spans = [
        _name_span("D", note.index("Dr."), replacement="James", pydeid_types=["Name Initial (PRE)"]),
        _name_span("r.", note.index("r."), replacement="Charles", pydeid_types=["Name9 (PRE)"]),
        _name_span("Michael", note.index("Michael"), replacement="Lindsey"),
        _name_span("Tan", note.index("Tan"), replacement="Alvarez"),
    ]

    text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(note, spans)

    assert warnings == []
    assert text == "Copy of note to family physician Dr. Lindsey Alvarez."
    assert final_spans[0].action == "preserved"
    assert final_spans[1].action == "preserved"
    assert final_spans[0].metadata["replacement_source"] == "project_title_token_veto"
    assert final_spans[1].metadata["replacement_source"] == "project_title_token_veto"
    assert final_spans[0].metadata["project_title_token_policy"] == "preserved_title_token_fragment"
    assert final_spans[1].metadata["project_title_token"] == "Dr."
    assert final_spans[2].metadata["replacement_source"] == "pyDeid"
    assert final_spans[3].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_preserves_split_dr_title_before_adjacent_name():
    note = "Copy of note to Dr. Michael Tan."
    spans = [
        _name_span("D", note.index("Dr."), replacement="James", pydeid_types=["Name Initial (PRE)"]),
        _name_span("r.", note.index("r."), replacement="Charles", pydeid_types=["Name9 (PRE)"]),
        _name_span("Michael", note.index("Michael"), replacement="Lindsey"),
        _name_span("Tan", note.index("Tan"), replacement="Alvarez"),
    ]

    text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(note, spans)

    assert warnings == []
    assert text == "Copy of note to Dr. Lindsey Alvarez."
    assert final_spans[0].metadata["replacement_source"] == "project_title_token_veto"
    assert final_spans[1].metadata["replacement_source"] == "project_title_token_veto"
    assert final_spans[0].metadata["project_title_token_context"] == "title_name_sequence"


def test_reconstruction_does_not_preserve_initial_outside_exact_dr_title_token():
    note = "Patient D. Smith attended."
    span = _name_span("D", note.index("D."), replacement="James", pydeid_types=["Name Initial (PRE)"])

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == "Patient James. Smith attended."
    assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_preserves_capitalized_action_word_with_generic_patient_object():
    note = "Dr. Examined the patient."
    span = _name_span("Examined", 4)

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == note
    assert warnings == []
    assert spans[0].action == "preserved"
    assert spans[0].metadata["replacement_source"] == "project_title_context_action_word_veto"
    assert spans[0].metadata["project_title_context_policy"] == (
        "title_context_capitalized_action_word_generic_patient_object_match"
    )
    assert spans[0].metadata["project_title_context_trigger"] == (
        "strict_title_name_heuristic_with_generic_patient_object"
    )


def test_reconstruction_preserves_capitalized_action_word_with_clinical_object():
    note = "Dr. Examined the chest wall."
    span = _name_span("Examined", 4)

    text, spans, warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == note
    assert warnings == []
    assert spans[0].action == "preserved"
    assert spans[0].metadata["replacement_source"] == "project_title_context_action_word_veto"
    assert spans[0].metadata["project_title_context_policy"] == (
        "title_context_capitalized_action_word_clinical_object_match"
    )
    assert spans[0].metadata["project_title_context_trigger"] == (
        "strict_title_name_heuristic_with_clinical_object"
    )
    assert spans[0].metadata["project_title_context_word"] == "examined"


def test_reconstruction_preserves_clinical_object_span_after_title_action_word():
    note = "Dr. Assessed skin toxicity as grade 1."
    spans = [
        _name_span("Assessed", 4),
        _name_span("skin", 13, replacement="Avery", pydeid_types=["Name (STitle)"]),
    ]

    text, final_spans, warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert text == note
    assert warnings == []
    assert final_spans[0].metadata["project_title_context_policy"] == (
        "title_context_capitalized_action_word_clinical_object_match"
    )
    assert final_spans[1].metadata["project_title_context_policy"] == (
        "title_context_clinical_object_after_action_match"
    )
    assert final_spans[1].metadata["project_title_context_word"] == "skin"


def test_reconstruction_preserves_capitalized_action_word_after_lowercase_dr():
    note = "dr. Reviewed mammography with tomosynthesis."
    span = _name_span("Reviewed", 4)

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == note
    assert spans[0].metadata["replacement_source"] == "project_title_context_action_word_veto"
    assert spans[0].metadata["project_title_context_policy"] == (
        "title_context_capitalized_action_word_clinical_object_match"
    )


def test_reconstruction_preserves_capitalized_action_word_after_dr_without_period():
    note = "Dr Assessed skin toxicity as grade 1."
    span = _name_span("Assessed", 3)

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == note
    assert spans[0].metadata["project_title_context_word"] == "assessed"


def test_reconstruction_does_not_preserve_capitalized_action_word_with_incomplete_context():
    for note in ["Dr. Examined the.", "Dr. Examined and."]:
        span = _name_span("Examined", 4)

        text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

        assert text != note
        assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_preserves_capitalized_action_word_after_clinical_role():
    note = "nurse Reviewed mammography with tomosynthesis."
    span = _name_span("Reviewed", 6)

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == note
    assert spans[0].metadata["replacement_source"] == "project_title_context_action_word_veto"
    assert spans[0].metadata["project_title_context_policy"] == (
        "role_context_capitalized_action_word_clinical_object_match"
    )
    assert spans[0].metadata["project_title_context_trigger"] == (
        "clinical_role_context_with_clinical_object"
    )


def test_reconstruction_preserves_capitalized_action_word_after_multiword_role():
    note = "Social worker Discussed transportation barriers."
    span = _name_span("Discussed", 14)

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == note
    assert spans[0].metadata["project_title_context_policy"] == (
        "role_context_capitalized_action_word_clinical_object_match"
    )


def test_reconstruction_preserves_role_action_with_generic_patient_object():
    note = "Oncologist Discussed the family."
    span = _name_span("Discussed", 11)

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == note
    assert spans[0].metadata["project_title_context_policy"] == (
        "role_context_capitalized_action_word_generic_patient_object_match"
    )


def test_reconstruction_does_not_preserve_capitalized_real_name_even_with_object_context():
    note = "Dr. Cook mammography with tomosynthesis."
    span = _name_span("Cook", 4)

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == "Dr. Carter mammography with tomosynthesis."
    assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_does_not_preserve_capitalized_real_name_after_role():
    note = "Nurse Taylor reviewed wound care."
    span = _name_span("Taylor", 6)

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == "Nurse Carter reviewed wound care."
    assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_preserves_lowercase_action_after_role_name_span():
    note = "Nurse Taylor reviewed wound care."
    spans = [
        _name_span("Taylor", 6, replacement="Bennett", pydeid_types=["First Name (Titles)"]),
        _name_span("reviewed", 13, replacement="Avery", pydeid_types=["Last Name (Titles)"]),
    ]

    text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert text == "Nurse Bennett reviewed wound care."
    assert final_spans[0].metadata["replacement_source"] == "pyDeid"
    assert final_spans[1].metadata["replacement_source"] == "project_title_context_action_word_veto"
    assert final_spans[1].metadata["project_title_context_policy"] == (
        "role_context_lowercase_action_word_clinical_object_after_name_match"
    )


def test_reconstruction_preserves_lowercase_action_after_title_name_span():
    note = "Dr. Solen discussed the patient."
    spans = [
        _name_span("Solen", 4, replacement="Bennett"),
        _name_span("discussed", 10, replacement="Avery", pydeid_types=["Name (STitle)"]),
    ]

    text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert text == "Dr. Bennett discussed the patient."
    assert final_spans[1].metadata["project_title_context_policy"] == (
        "title_context_lowercase_action_word_generic_patient_object_after_name_match"
    )


def test_reconstruction_does_not_preserve_lowercase_action_after_role_name_without_object():
    note = "Nurse Taylor reviewed."
    spans = [
        _name_span("Taylor", 6, replacement="Bennett", pydeid_types=["First Name (Titles)"]),
        _name_span("reviewed", 13, replacement="Avery", pydeid_types=["Last Name (Titles)"]),
    ]

    text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert text == "Nurse Bennett Avery."
    assert final_spans[1].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_does_not_preserve_lowercase_action_after_patient_alias_name():
    note = "Nurse Taylor reviewed wound care."
    spans = [
        _name_span("Taylor", 6, replacement="Bennett", pydeid_types=["Custom Patient First Name"]),
        _name_span("reviewed", 13, replacement="Avery", pydeid_types=["Last Name (Titles)"]),
    ]

    text, final_spans, _warnings = reconstruction._reconstruct_with_project_replacements(
        note,
        spans,
    )

    assert text == "Nurse Bennett Avery wound care."
    assert final_spans[1].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_does_not_preserve_role_action_without_following_context():
    note = "Surgeon Discussed."
    span = _name_span("Discussed", 8)

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == "Surgeon Carter."
    assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_does_not_preserve_action_word_without_title_context():
    note = "The note reviewed mammography."
    span = _name_span("reviewed", 9, replacement="Avery", pydeid_types=["Name (STitle)"])

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == "The note Avery mammography."
    assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_reconstruction_patient_alias_wins_over_action_word_veto():
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
    note = "Dr. reviewed the patient."
    span = _name_span("reviewed", 4)

    monkeypatch.setattr(title_context, "_load_pydeid_name_words", lambda: frozenset({"reviewed"}))

    text, spans, _warnings = reconstruction._reconstruct_with_project_replacements(note, [span])

    assert text == "Dr. Carter the patient."
    assert spans[0].metadata["replacement_source"] == "pyDeid"


def test_deidentify_note_preserves_title_context_action_words_from_pydeid():
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


def test_deidentify_note_preserves_split_dr_title_after_role_from_pydeid():
    note = "Copy of note to family physician Dr. Michael Tan."

    result = deidentify_note(note)

    assert "family physician Dr. " in result.deidentified_text
    assert "Michael Tan" not in result.deidentified_text
    assert any(
        span.text == "D"
        and span.metadata.get("replacement_source") == "project_title_token_veto"
        and span.metadata.get("project_title_token_policy") == "preserved_title_token_fragment"
        for span in result.spans
    )
    assert any(
        span.text == "r."
        and span.metadata.get("replacement_source") == "project_title_token_veto"
        for span in result.spans
    )


def test_deidentify_note_preserves_protected_term_plus_following_action_word():
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


def test_deidentify_note_preserves_capitalized_title_action_with_clinical_object():
    note = "Dr. Examined the chest wall. Dr. Assessed skin toxicity as grade 1."

    result = deidentify_note(note)

    assert result.deidentified_text == note
    assert any(
        span.metadata.get("replacement_source") == "project_title_context_action_word_veto"
        and span.metadata.get("project_title_context_policy")
        == "title_context_capitalized_action_word_clinical_object_match"
        for span in result.spans
    )
    assert any(
        span.text == "skin"
        and span.metadata.get("project_title_context_policy")
        == "title_context_clinical_object_after_action_match"
        for span in result.spans
    )


def test_deidentify_note_preserves_capitalized_title_action_with_generic_patient_object():
    note = "Dr. Examined the patient."

    result = deidentify_note(note)

    assert result.deidentified_text == note
    assert any(
        span.metadata.get("project_title_context_policy")
        == "title_context_capitalized_action_word_generic_patient_object_match"
        for span in result.spans
    )


def test_deidentify_note_preserves_role_context_action_words_from_pydeid():
    note = "Nurse Reviewed wound care. Nurse Taylor reviewed wound care."

    result = deidentify_note(note)

    assert "Nurse Reviewed wound care." in result.deidentified_text
    assert "reviewed wound care" in result.deidentified_text
    assert "Taylor" not in result.deidentified_text
    role_policies = {
        span.metadata.get("project_title_context_policy")
        for span in result.spans
        if span.metadata.get("replacement_source") == "project_title_context_action_word_veto"
    }
    assert "role_context_capitalized_action_word_clinical_object_match" in role_policies
    assert "role_context_lowercase_action_word_clinical_object_after_name_match" in role_policies


def test_deidentify_csv_audit_records_title_context_metadata(tmp_path):
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


def test_deidentify_csv_audit_records_title_token_metadata(tmp_path):
    input_file = tmp_path / "input.csv"
    output_file = tmp_path / "output.csv"
    audit_file = tmp_path / "audit.csv"
    _write_csv(
        input_file,
        [
            {
                "patient_id": "Patient/synth-title-002",
                "note_id": "Note/synth-title-002",
                "note_text": "Copy of note to family physician Dr. Michael Tan.",
            }
        ],
    )

    summary = deidentify_csv(input_file, output_file, audit_output_file=audit_file)

    output_rows = _read_csv(output_file)
    audit_rows = _read_csv(audit_file)
    title_token_rows = [
        row for row in audit_rows if row["replacement_source"] == "project_title_token_veto"
    ]
    assert summary["rows_failed"] == 0
    assert "family physician Dr. " in output_rows[0]["note_text"]
    assert "Michael Tan" not in output_rows[0]["note_text"]
    assert title_token_rows
    assert {row["project_title_token"] for row in title_token_rows} == {"Dr."}
    assert title_token_rows[0]["project_title_token_policy"] == "preserved_title_token_fragment"
