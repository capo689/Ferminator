---
name: ferminator-profile-builder
description: Build, revise, or calibrate a Ferminator schema-v2 career decision profile from a resume, confirmed LinkedIn/GitHub/portfolio sources, application history, and a guided interview. Use when onboarding a Ferminator user, converting career materials into validated Ferminator Markdown, defining role-family retrieval and Great/Maybe/Wrong rules, validating an existing profile, or refining it from real-job feedback without inventing qualifications.
---

# Ferminator Profile Builder

Produce one validated `<first-name>-<last-name>.md` profile that Ferminator can
ingest without manual reformatting. Build an evidence-backed job-decision model,
not a promotional résumé.

## Required resources

Read before beginning:

- `references/profile-contract.md` for schema v2 and decision semantics.
- `references/evidence-rules.md` before using supplied or public evidence.
- `references/interview-guide.md` before interviewing.

Use `assets/profile-template.md` as the skeleton. Run
`scripts/validate_profile.py` when filesystem execution is available.

## Workflow

1. **Inventory inputs.**
   - Require a résumé or equivalent career history.
   - Request confirmed professional URLs and an optional application ledger.
   - Ask permission before public discovery of missing professional sources.

2. **Resolve identity and evidence.**
   - Require user confirmation before attributing public profiles.
   - Build a ledger of claims, sources, confidence, conflicts, and non-claims.
   - Use only user-provided or source-supported claims in the final profile.

3. **Interview in short rounds.**
   - Ask no more than five questions at once.
   - Resolve career evidence before preferences.
   - Capture scope, ATS credibility, role intent, constraints, company
     preferences, undesirable work patterns, and duplicate history.

4. **Design role families.**
   - Classify each as core, adjacent, edge, or exploratory.
   - Translate intent to internal tier and starting threshold using the
     contract. Never ask the user to interpret raw score thresholds.
   - Add must-involve work, required context, false positives,
     disqualifying responsibilities, evidence, tolerated gaps, and non-claims.
   - Keep retrieval vocabulary broad enough for abundance while using
     contextual rules to prevent keyword collisions.

5. **Design the decision model.**
   - Separate retrieval, eligibility gates, predicted desirability, and human
     verdict.
   - Define Great, Maybe, and Wrong using concrete evidence and tradeoffs.
   - Use the canonical Wrong taxonomy.
   - Treat geography, compensation floors, travel, and mandatory gaps as gates
     or manual-review conditions rather than token score adjustments.

6. **Configure practical rules.**
   - Capture full-time and contract economics separately.
   - Capture remote region, ZIP/radius, timezone, hybrid, travel, relocation,
     and exceptions.
   - Encode unresolved hybrid, relocation, and economic exceptions as `null`;
     never turn an unknown preference into permission or rejection.
   - Apply the default source-aware freshness policy unless explicitly changed.
   - Default email off. Record schedule preference while stating that the beta
     administrator assigns the actual run slot.
   - Make `max_daily_matches` a digest cap only.

7. **Generate and validate.**
   - Copy the template and replace every placeholder.
   - Preserve YAML types and schema-v2 keys.
   - Run the standalone validator and, when available,
     `ferminator profile validate`.
   - If scripts cannot run, perform the same contract checks in context and
     label the result `structurally reviewed`, not machine-validated.
   - Fix every error before delivery.

8. **Calibrate with real jobs.**
   - Trigger a broad first run after account creation.
   - Request a diverse 20–40-job review when supply permits.
   - Capture reasons for Great, Maybe, Wrong, and Duplicate.
   - Recalibrate positive recall, Wrong rejection, and Great-versus-Maybe
     ordering. Never tighten merely to manufacture a small result count.

9. **Deliver.**
   - Provide the profile and separate source-coverage report.
   - Disclose unresolved evidence and conservative choices.
   - Mark calibration `provisional` until real-job review is complete.
   - Do not silently revise confirmed facts during formatting.

## Completion gate

Finish only when:

- identity-sensitive sources are confirmed;
- role families contain decision rules and evidence;
- retrieval, eligibility, desirability, and human verdict are distinct;
- geography, economics, freshness, work patterns, and duplicate history are
  explicit;
- schema-v2 ranking weights total 100;
- email and digest behavior are correctly scoped;
- no placeholders or secrets remain;
- every available validator reports success;
- unresolved gaps and calibration status are disclosed.
