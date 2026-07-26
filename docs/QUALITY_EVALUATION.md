# Match-quality evaluation

Ferminator treats recommendation quality as a release gate, not a dashboard
opinion.

`tests/golden/adam-match-quality.yaml` contains human-labelled strong, review,
and wrong opportunities. Run:

```bash
ferminator quality-eval
```

The gate fails below 80% exact tier accuracy or when any known-wrong role is
surfaced as review or strong. Add a regression case before changing a matching
rule in response to real dashboard feedback.

The dashboard records `great`, `maybe`, and `wrong` verdicts against the exact
job revision, profile version, score, and component scores. The Intelligence
view reports the useful-match rate. Feedback does not silently rewrite ranking
weights; a human reviews the evidence, adds a representative golden case, then
changes and tests the deterministic rules.

Live verification on 2026-07-25 covered all 54 enabled boards across six ATS
providers. Every board normalized successfully: 6,096 jobs total. The initial
market pass found that `FullTime` and `Permanent Full Time Employee` were being
rejected against the profile's `full-time`; canonical employment-type matching
was added and protected with regression tests.

## Calibration V2

`calibration/v2/corpus.jsonl` freezes Adam's complete review of 61 Discover
jobs from 2026-07-26. It includes the complete JD and long-form review for:

- 11 Great
- 8 Maybe
- 40 Wrong
- 2 Duplicate

Run the V2 gate with:

```bash
pytest tests/test_ferminator_calibration_v2.py
```

The gate requires:

- all 19 Great/Maybe jobs remain visible;
- at least 34 of 40 Wrong jobs remain below the visibility boundary;
- the corpus SHA-256 remains unchanged unless the calibration version is
  intentionally replaced.

V2 distinguishes functional alignment from conventional eligibility and
opportunity economics. A copy role rejected for low pay must not teach the
matcher that copywriting is a bad function. Likewise, an AI-labelled
engineering role must not rank highly merely because its description contains
agents, APIs, workflows, or adoption language.

The live profile can be rescored without fetching every ATS board:

```bash
ferminator rescore --profile-path profiles/adam-cagle.md
```
