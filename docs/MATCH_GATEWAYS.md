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
   career function named in the title. Explicit residency-timezone conflicts
   and travel above the profile's configured ceiling also stop here.
4. **Compensation** — reject only explicitly incompatible annual or hourly
   ranges. Missing compensation advances with an uncertainty flag.
5. **Refined fit** — rank career evidence, role alignment, skills, seniority,
   geography, compensation, freshness, and function-specific calibration.
6. **Application and duplicate review** — exact ATS/URL identity is handled
   cheaply during ingestion. After refined matching, identical normalized
   company/title listings from overlapping boards collapse to the richest
   representative and share profile feedback, so Wrong or Duplicate cannot
   reappear through a sibling board record. Application-history and fuzzy title
   comparison then run only for surviving jobs.

Every rescore prints the number of jobs rejected or accepted at each gateway.
The production workflow then runs `discover-audit`, which reproduces role
thresholds, feedback suppression, application-ledger suppression, and default
geography. The production audit requires a non-empty Discover result. Match
quality and abundance are measured separately: the calibration gate protects
every reviewed positive, while market counts are reported without forcing the
matcher to pad the page to an arbitrary quota.

The 85-job Calibration V3 corpus is the current quality invariant:

- all 26 reviewed Great and Maybe jobs must remain visible;
- all 57 reviewed Wrong jobs must be rejected by matching;
- Duplicate feedback remains profile-specific and reversible.
