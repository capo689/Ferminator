# Ferminator Calibration Export V1

## What is included

- 58 unique historical job reviews
- 58 job URLs
- 58 captured job descriptions
- 23 normalized Apply recommendations
- 17 Consider recommendations
- 8 Stretch recommendations
- 10 Pass recommendations
- 22 records with a recoverable Adam verdict
- Initial retrieval score and final reviewer score stored separately when both exist
- Confirmed application, pass, and pending-decision outcomes joined from the job ledger

## Important limitation

The historical dashboard field named `full_jd` often contains a detailed, faithful condensation of the listing rather than the complete verbatim posting. Every record identifies this as:

`dashboard_full_jd_field_often_condensed`

Ferminator must not silently treat these descriptions as verbatim archival copies. They are sufficient for an initial calibration set, but the highest-value records should eventually be replaced with exact listing text from the original saved page or attachment.

## The scoring architecture Ferminator should learn

One number cannot safely represent the whole decision. Keep these values separate:

1. **Functional fit:** How closely the actual work matches Adam's evidence.
2. **Eligibility:** Whether location, authorization, language, clearance, degree, license, compensation, or employment terms permit an application.
3. **Application priority:** Whether Adam should spend time applying now.
4. **Resume plausibility:** Whether a truthful tailored resume can make the case.
5. **Interview likelihood:** Estimated probability of receiving a human response.
6. **Adam verdict:** Yes, maybe, or no.

A role can have a functional-fit score of 97 and still be an automatic pass because it requires three days each week in New York.

## Required provenance fields

Every future record should preserve:

- Canonical company ATS URL
- Discovery URL and source platform
- External requisition ID
- Normalized duplicate key
- Exact raw description
- Description hash
- Retrieval timestamp
- Live-verification timestamp
- Reviewer version
- Scoring-policy version
- Final human-decision timestamp
- Outcome-event history

Do not overwrite prior judgments. Append a new evaluation event when the reviewer, policy, or user changes a score.

## Hard-gate structure

Hard gates should be structured, not buried in prose:

```json
{
  "eligibility": {
    "passed": false,
    "gates": [
      {
        "type": "geography",
        "required": "NYC residence and three office days per week",
        "adam_status": "Bend, Oregon",
        "result": "fail",
        "evidence": "Exact excerpt from listing"
      }
    ]
  }
}
```

Recommended gate types:

- Geography
- Remote-state eligibility
- Compensation
- Work authorization
- Language
- Clearance
- License or certification
- Degree
- Required years in a specific discipline
- Travel
- Full-time, contract, or employment arrangement
- Required technical depth

## Outcome history

Use an event list instead of one mutable status:

```json
{
  "outcome_events": [
    {
      "event": "reviewed",
      "date": "2026-07-24"
    },
    {
      "event": "applied",
      "date": "2026-07-24"
    },
    {
      "event": "interview_requested",
      "date": "2026-07-26"
    }
  ]
}
```

This prevents `interviewing` from erasing the fact that the application was submitted and prevents `rejected` from being confused with Adam choosing to pass.

## Real pairwise calibration judgments

### Loka above Evertune for application priority

- **Loka, Senior Content & Communications Lead:** Final fit 96, remote, applied.
- **Evertune, AI Strategist, SEO & GEO:** Final functional fit 97, but required NYC residence and three office days per week, so Adam passed.

Evertune can score higher on function while Loka ranks higher for action. Eligibility must be applied after functional scoring and before application priority.

### Hightouch above Branch

- **Hightouch, Go-to-Market Engineer:** Fit 85, remote, compensation in range, applied.
- **Branch, Copywriter & AI Content Systems Designer:** Functional fit 95, but Oregon was excluded and the compensation ceiling was below Adam's normal target.

Branch is the stronger description match. Hightouch is the stronger real opportunity.

### Figma above Misfits & Machines

- **Figma, Marketing Engineer (AI Deployment):** Fit 88, business-facing AI workflows, MCP, prompt systems, adoption, and marketing context. Applied.
- **Misfits & Machines, AI Architect:** Initial fit 65 and a stretch because five-plus years of formal software engineering plus TypeScript and Node proficiency were central.

Keyword overlap around agents, prompts, evaluation, and creative AI must not hide a conventional engineering requirement.

### Intradiem above Backblaze for Adam's evidence

- **Intradiem, Director of Enterprise AI Enablement:** Fit 82 and applied after tailoring around client leadership, enablement, governance, and hands-on AI systems.
- **Backblaze, AI Enablement Director:** Initially scored 84, but Adam correctly challenged the rating because formal enterprise-wide AI-program ownership, vendor governance, and quantified transformation outcomes were more central than the score acknowledged.

This is an example where the initial score should be reviewed downward. Adjacent leadership experience is not automatically equivalent to formal enterprise program ownership.

### Functional match does not defeat a language gate

- **Zeely, AI Marketing Automation Engineer:** Strong work match across AI content systems and marketing automation.
- Final decision: Pass after the Ukrainian-language requirement was discovered.

Language requirements must be checked before resume production.

### A company is not disqualified when one role is

- **Zillow, Senior AI Program Manager, Talent:** Pass because the function was HR and talent enablement.
- **Zillow:** Remains eligible for product, marketing, content, AI workflow, and other relevant roles.

Store disqualifiers at the job level unless evidence explicitly supports a company-wide exclusion.

## Recommended use of this file

1. Use the 58 records as the first regression corpus.
2. Train and test functional-fit ordering separately from hard eligibility.
3. Use only the 22 records with known Adam reactions for human-preference calibration.
4. Do a fast Yes / Maybe / No adjudication pass on the remaining records.
5. Replace condensed descriptions with verbatim archived listings for the most important 50 examples.
6. Add interview and rejection events as they happen.
7. Freeze this dataset as V1 before changing scoring rules.

## Files

- `ferminator-calibration-v1.jsonl`
- `ferminator-calibration-v1-report.json`
- `ferminator-calibration-v1-notes.md`
