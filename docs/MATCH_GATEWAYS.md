# Match gateways

Ferminator evaluates jobs using the largest safe cuts first. Early gateways
optimize recall: uncertainty advances, while only reliable incompatibilities
reject.

1. **Geography** — accept US-compatible remote work and configured local
   geography; reject clearly incompatible regions.
2. **Functional recall** — accept a configured title family, or an
   unconventional title whose JD contains both a role-family signal and a
   major profile concept.
3. **Hard disqualifiers** — reject excluded career functions, mandatory
   incompatibilities, unsupported employment types, adjacent roles without
   supporting JD evidence, and JD-inferred families that do not agree with the
   career function named in the title.
4. **Compensation** — reject only explicitly incompatible annual or hourly
   ranges. Missing compensation advances with an uncertainty flag.
5. **Refined fit** — rank career evidence, role alignment, skills, seniority,
   geography, compensation, freshness, and function-specific calibration.
6. **Application and duplicate review** — exact ATS/URL identity is handled
   cheaply during ingestion. After refined matching, identical normalized
   company/title listings from overlapping boards collapse to the richest
   representative. Application-history and fuzzy title comparison then run
   only for surviving jobs.

Every rescore prints the number of jobs rejected or accepted at each gateway.
The production workflow then runs `discover-audit`, which reproduces role
thresholds, feedback suppression, application-ledger suppression, and default
geography. Adam's release gate requires at least 40 opportunities in the actual
default Discover result.

The 61-job Calibration V2 corpus remains the quality invariant:

- all reviewed Great and Maybe jobs must remain visible;
- all reviewed Wrong jobs must be rejected by matching or hidden by explicit
  feedback;
- Duplicate feedback remains profile-specific and reversible.
