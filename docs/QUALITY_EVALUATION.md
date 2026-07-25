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
