from project_phi import deidentify_note

note_1 = (
    "Patient Zylanda Qorven was seen by Dr. Mira Solen on April 10, 2001 at 14:30. "
    "Her sister Amari Qorven reported nausea after cycle 2 chemotherapy. "
    "Dr. Tomosynthesis reviewed mammography with tomosynthesis. "
    "Diagnosis was documented in March 2021 and endocrine therapy started in October 2021. "
    "Plan: continue ondansetron, repeat CBC in 7 days, and review in spring 2001. "
    "Call 416-555-0199 or zylanda.synthetic@example.invalid if symptoms worsen."
)

note_2 = (
    "Copied note: Dear Dr. Ivo Laren, Zylanda Qorven attended the clinic. "
    "Original letter from Dr. Rowan Vale also served as the referring contact. "
    "Diagnosis remains asthma exacerbation; oxygen saturation was 94% on room air."
)

note_3 = (
    "Started prednisone on 2001-01-05 and stopped on 2001-01-12. "
    "The note references the 2020 guideline, 08:15 vitals, winter symptoms, and stage 2 disease."
)

result = deidentify_note(
    note_3,
    patient_id="Patient/synthetic-001",
    note_id="Note/synthetic-001",
    stable_date_shift=True,
    date_shift_secret="synthetic-demo-secret",
)
print(result.deidentified_text)