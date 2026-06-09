# Semantic Preservation

## Purpose

The pipeline is designed for internal training-candidate preparation where
clinical meaning matters. The goal is not to delete every suspicious string at
any cost. The goal is to reduce obvious identifier risk while preserving
clinically useful structure and terminology.

## Date Semantics

Stable date shifting uses pyDeid-detected date spans and applies one
patient-specific offset across a patient's notes. This preserves within-patient
date intervals, unlike independent random replacement.

The project shifts parseable full dates, including ISO-style dates and common
English month-name dates in both month-day-year and day-month-year forms, only
when pyDeid has already emitted a date span. Examples include
`March 14, 2026`, `8 August 2019`, and comma-separated day-month-year forms
such as `15 August, 2003`. It also shifts pyDeid-detected month/year spans
such as `March 2021` while preserving month/year granularity. Month/year
shifting uses the same patient-specific day offset as full dates with an
internal day-15 anchor, then outputs only `Month YYYY`.

Month/day spans without a year, such as `July 15`, are shifted by default. The
implementation uses an internal leap-year anchor for month rollover and outputs
only `Month Day`.

The project does not add a separate date detector. Year-only mentions, times,
seasons, and holidays are preserved by default.

Some clinical scores and ratios use date-like slash notation. When pyDeid emits
text such as `1/50`, `11/50`, `1/61`, or `6/60` as a date-like span, ProjectPHI
checks bounded local context for score, scale, staging, node-count, ratio, or
visual-acuity cues. If those cues are present, it preserves the original
notation instead of shifting it to a month/year phrase. This is still
span-local; it does not scan the full note for new scores. Three-part
Apgar-style slash scores such as `4/7/10` are preserved only when nearby text
also contains Apgar wording and 1/5/10-minute timing cues, so ordinary slash
dates remain eligible for stable date shifting. Tumor-marker fragments such as
`CA 15-3` are preserved only when bounded local context indicates tumor-marker
use.

## Decimal-Code Semantics

pyDeid can mistake dotted numeric code fragments for phone numbers. ProjectPHI
preserves pyDeid-emitted contact spans such as `189.1000043` when their dotted
digit grouping is not phone-like, or when a colon/dotted continuation shows a
larger code shape. Phone-like dotted contact text such as `416.555.1212`
continues to be replaced. It also preserves long floating-point measurement
fragments in strong measurement context, such as tumor-size values ending in a
long decimal tail, so pyDeid does not turn them into phone-like surrogates.
Short unit cues such as `cm` and `mm` are matched as bounded measurement tokens,
not as substrings inside ordinary words.

## Clinical Abbreviation Semantics

pyDeid can emit `PMH` as a site acronym inside `PMHx`. ProjectPHI preserves the
pyDeid-emitted `PMH` span when it is immediately followed by `x` or `X`, so the
common clinical shorthand `PMHx` remains intact. ProjectPHI also preserves
standalone `PMH` only in bounded past-medical-history context, and selected
short abbreviations such as `NIA`/`AA` in `NIA-AA`, `SAH`, `MSH`, `WES`, `SAM`,
or `AMAN` only when nearby context supports a specific clinical meaning.

## Obstetric-History Semantics

Strict obstetric-history shorthand such as `G1P0A0` is clinically meaningful
and can look like an identifier. ProjectPHI preserves pyDeid-emitted spans that
exactly match conservative `G/P/A/L/T` shorthand patterns. It does not scan the
full note for these patterns and does not preserve arbitrary alphanumeric study
codes.

## Ordinary-Token Semantics

pyDeid can sometimes emit very short ordinary tokens as `NAME` spans. ProjectPHI
preserves a small set of high-confidence articles and pronouns, such as `a`,
`An`, `He`, and `Her`, when local context does not look like an initial or case
label. It also preserves `NH` only in guarded nursing-home shorthand contexts.

This is intentionally conservative. ProjectPHI does not preserve arbitrary
short uppercase tokens, and it does not override pyDeid in contexts such as
`A. Smith`, `Dr. A`, `Patient A`, `Subject A`, or `Case A`.

ProjectPHI also preserves a lowercase `t` span only when pyDeid appears to
have split the word `at` immediately before numeric, time, or measurement
context, such as `at 10 weeks' gestation` or `at 5 pm`. It does not preserve
arbitrary `t` initials or `at` before locations, facilities, or ordinary words.

## Patient Name Semantics

Stable patient-name surrogates require explicit aliases. The wrapper does not infer
patient aliases from notes because notes may contain patient, clinician, family,
copied-correspondence, facility, and organization names.

When aliases are missing and stable patient-name surrogates are enabled for CSV,
the row fails through the sanitized row-failure path. If stable patient-name
surrogates are disabled, pyDeid still replaces names, but those replacements may
not be stable across notes for the same patient.

When aliases are supplied, ProjectPHI uses pyDeid name detection where possible
and then performs a bounded exact residual pass for supplied aliases that pyDeid
missed or pruned. This improves recall for governed patient alias manifests
without turning the wrapper into a general person-name detector. Unknown names,
clinician names, family names, copied-correspondence names, facilities, and
organizations are not inferred as patient aliases.

For explicit patient aliases, the project uses a deterministic Faker-generated
fake identity keyed by `patient_id` and a runtime secret. The replacement is
role-preserving but not gender-concordant: the wrapper does not infer gender
from breast oncology context, names, pronouns, or diagnosis because that would
add an unvalidated inference layer and can create incorrect assumptions.

## Provider Name Semantics

Stable provider-name surrogates require explicit provider aliases from governed
runtime configuration. The wrapper does not infer provider aliases from notes,
provider-role words, signatures, copied correspondence, or name-like tokens.

When provider aliases are supplied, ProjectPHI uses pyDeid name detection where
possible and then performs a bounded exact residual pass for configured aliases
that pyDeid missed or pruned. Full aliases can match exactly. Single-token
aliases require local provider-role context, such as `Radiologist Chen`,
`Social worker Green`, or an adjacent `MD` marker, so configured names that are
also ordinary words are not replaced globally.

Provider replacements use deterministic fake identities keyed by `provider_id`
and a runtime secret. Unknown names and unconfigured provider names remain
pyDeid behavior.

## Protected Clinical Terms

Protected clinical terms reduce false positives where pyDeid flags clinically
meaningful text as PHI. The mechanism is span-local:

- it inspects only pyDeid-detected/pruned spans;
- it uses exact normalized whole-span matching;
- it does not scan the full note;
- it does not create new spans;
- it does not use fuzzy matching, stemming, NER, or LLMs.

The current built-in list is manually curated, general, and non-site-specific.
It covers selected breast imaging/mammography, breast imaging findings,
breast cancer pathology, receptor/biomarker status, staging,
metastasis/recurrence, systemic/endocrine therapy, radiology/imaging,
treatment, surgery/radiation, disease-status terms, selected clinical
tools/scales/criteria, and selected phrase-bound scientific fragments.

Some clinical tools contain words that are also plausible names or places, such
as `Chelsea` in `Chelsea Critical Care Physical Assessment Tool`. ProjectPHI
does not protect those components globally. Instead, phrase-component
protection can preserve the pyDeid-emitted component only when the bounded
source-text context matches an approved clinical phrase. This keeps the rule
span-local and avoids turning risky eponyms into blanket allow-list entries.
The same approach is used for selected observed fragments such as `Paddick` in
`Paddick index`, `Hamilton` in Hamilton scales, `Willebrand` in
`von Willebrand factor`, `P.` in `P. insidiosum`, `GIA` in `Endo-GIA`, `M` in
`Sof-lex/3 M ESPE`, `Jackson`/`Pratt` in `Jackson-Pratt`, `McFarland` in
`0.5 McFarland`, `au` in `cafe-au-lait`, `veno` in `veno-venous` or
`veno-occlusive disease`, `hemi` in `hemi-abdomen`, `hemi-diaphragm`,
`hemi-thorax`, `hemi-trigone`, or `hemi-CRVO`, `Fuhrman` in
`Fuhrman nuclear grade`, `Allred` in Allred scoring terms, `Scarff` in
`Scarff-Bloom-Richardson`,
`Cormack`/`Lehane` in `Cormack-Lehane`, and `dermo` in
`dermo-hypodermal`. Additional guarded eponym/fragment examples include
`Ishak` in fibrosis staging, `Grocott` in stain contexts, `Hertel` in
exophthalmometry contexts, `Naranjo` in adverse-drug-reaction probability
scale contexts, and `de`/`sac` only in bounded `cul-de-sac` phrases.

Residual risk is explicit: a rare person, facility, or organization could share
a protected clinical term. That tradeoff is accepted only for internal
training-candidate generation and should be reviewed before governed use.

The built-in list is now considered the stable public baseline. Further
semantic-preservation expansion should generally be driven by governed local
evaluation and supplied as runtime protected-term CSV artifacts. 

## Compact Clinical Codes

ProjectPHI also preserves selected compact clinical codes and short clinical
phrases when pyDeid has already emitted them as spans and bounded context
strongly supports a clinical read. Examples include GCS components such as
`E2V2M5`, TNM stages such as `T3N0M0`, contextual biomedical abbreviations such
as `STEC`, `WM`, `EBER`, `HAMN`, `GNAS`, `ROIs`, `JC`, and clinical exposure
phrases such as `10 days drive`. Long genomic coordinate ranges are preserved
only when bounded cytogenetic or molecular context supports that read, such as
CGH array, FISH, chromosome, `chr` coordinates, genomic alterations, deletion,
breakpoint, or base-pair wording. If pyDeid emits overlapping time, SIN, or
phone-like spans inside such genomic coordinate tokens, ProjectPHI drops those
overlapping spans before reconstruction instead of failing the row.
Additional context-bound eponyms and report fragments are preserved only when
nearby wording supports a clinical/report reading, such as `Lauren` in gastric
pathology classification, `FUHRMAN` in nuclear-grade context, `ASMA` in
anti-smooth-muscle antibody context, `URA` only as a standalone
upper-renal-artery abbreviation, or OCR/template fragments such as `IMM`, `AXT`, `KER`,
`MAK`, `LYM`, `FS`, `Coll`, and `Grou` in bounded pathology report fields.
Pathology report
headers such as `MICROSCOPIC`, `ADDENDUM`, `Specimen`, `Margins`, `FINAL`, and
`Tumor` are preserved only with nearby report-template cues. Ordinary words
such as `Comment`, `History`, and `margin` require the same bounded pathology
or report context.

ProjectPHI separately preserves selected ordinary clinical prose when pyDeid
emits it as a `NAME` span in strong local context, such as `Blood` in `Blood
pressure`, `Vital` in `Vital signs`, `Computed tomography`, `follow-up`, and
similar low-risk clinical wording. For internal semantic preservation, exact
bounded terms such as `follow-up`, `homecare`, `low-income`,
`diabetes mellitus`, and `do-not-resuscitate` are treated as low-risk clinical
or care-context text when pyDeid emits them as spans. It also preserves
selected vendor or reference metadata such as `Varian`, `Caris`, `Promega`,
`Dako`, `Webster`, `Johnson`, `VITEK`, `SOFIA`, `Agilent`, `Kerr`, `Zeiss`,
`Vysis`, `Vinci`, `Stryker`, `Zimmer`, `Somanetics`, `Mayfield`, `Bayer`,
`Tomey`, `Abbott`, `Roche`, and `Siemens` only when nearby product, assay,
manufacturer, or device context supports that read. Additional source/device
tokens such as `Philips`
are handled the same way. Highly name-like vendor tokens such as `Smith`,
`Ramsey`, and `Mayfield` require product-specific cues rather than generic
device or wound-care wording.
Geography is not preserved by this rule; city/country names remain pyDeid
fallback unless another explicit project rule applies.

This is intentionally not a general identifier allow-list. Production
deployments should mask known patient IDs, provider names, accession numbers,
MRNs, local study IDs, and site-specific codes with explicit lists or custom
regexes.

## Title-Context Action Words

pyDeid can sometimes treat clinical action words after short titles as name
spans, for example `examined` in `The Dr. examined the patient`, `reviewed` in
`Dr. Solen reviewed mammography`, or `Reviewed` in `Dr. Reviewed mammography`.
ProjectPHI adds a narrow span-local veto for this false-positive class,
including selected clinical-role contexts such as nurse, surgeon, oncologist,
radiologist, pathologist, pharmacist, physiotherapist, and social worker.

The veto only applies to pyDeid-emitted title-derived `NAME` spans. It requires
an exact match to a curated clinical/documentation action-word list, a narrow
`Dr.` or clinical-role context, no explicit custom patient/provider alias, and
absence from pyDeid name lists. Lower-case action words use the base `Dr.` rule.
Capitalized action words are preserved only when specific clinical-object
context follows, such as `mammography`, `chest wall`, `skin toxicity`, or
`stable disease`, or when generic patient/person context follows, such as
`the patient` or `the family`. It does not scan the full note. If pyDeid also
emits the following clinical object as a title-derived name span, ProjectPHI can
preserve that adjacent object as part of the same false-positive title/action
pattern. It can also preserve a lower-case action word immediately after a
replaced role/title name span, such as preserving `reviewed` in
`Nurse <name> reviewed wound care`.

A separate, narrower title-token-fragment veto preserves non-identifying `Dr.`
fragments when pyDeid splits the title token itself into name spans, for
example after `family physician`. This keeps text such as
`family physician Dr. <name surrogate>` readable while the clinician name uses
pyDeid replacement unless an explicit stable provider-name policy applies.

This prioritizes semantic preservation for common documentation verbs while
keeping pyDeid replacement as the fallback in ambiguous cases.

## External Terminology Source Policy

Larger externally derived protected-term lists should be governed runtime
artifacts passed with `--protected-clinical-terms-csv`, not committed to the
public repository.

pyDeid internal wordlists, including `sno_edited.txt`, are used only through
pyDeid runtime behavior. 

Recommended sidecar metadata for governed protected-term CSV artifacts:

```json
{
  "artifact_version": "synthetic-2026-05-16",
  "review_status": "reviewed",
  "governance_owner": "approved curator role",
  "approval_review_date": "2026-05-16",
  "sources": [
    {
      "source_name": "Synthetic terminology source",
      "source_version": "example",
      "source_release_date": "2026-05-01",
      "source_url": "https://example.invalid/synthetic-source",
      "source_license": "example license",
      "extraction_date": "2026-05-16",
      "extraction_method": "documented exact-term extraction and manual review"
    }
  ]
}
```
