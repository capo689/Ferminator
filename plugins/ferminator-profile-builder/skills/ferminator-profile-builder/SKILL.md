---
name: ferminator-profile-builder
description: Build or revise a Ferminator career-search profile from a resume, confirmed LinkedIn/GitHub/portfolio sources, and a guided user interview. Use when onboarding a Ferminator user, converting career materials into Ferminator YAML-front-matter Markdown, validating an existing Ferminator profile, or filling evidence and search-preference gaps without inventing qualifications.
---

# Ferminator Profile Builder

Produce one validated `<first-name>-<last-name>.md` profile that Ferminator can
ingest without manual reformatting. Optimize for factual match quality, not for
making the user appear qualified for every role.

## Required resources

Read these files before beginning:

- `references/profile-contract.md` for the canonical schema and defaults.
- `references/evidence-rules.md` before reading resumes or public webpages.
- `references/interview-guide.md` before asking onboarding questions.

Use `assets/profile-template.md` as the output skeleton. Run
`scripts/validate_profile.py` against the finished file.

## Workflow

1. **Inventory the inputs.**
   - Require a resume or equivalent career-history document.
   - Ask for LinkedIn, GitHub, portfolio, personal-site, and relevant project
     URLs. Treat each as optional unless it matters to the target work.
   - Ask whether the user wants public-source discovery for missing URLs.

2. **Resolve identity safely.**
   - Never assume a search result belongs to the user.
   - Show candidate public profiles with enough context to distinguish them,
     then require the user to confirm each one before using it.
   - Do not bypass authentication, scrape login-restricted pages, or request
     passwords. Ask for a URL, PDF export, or pasted profile instead.

3. **Build an evidence ledger.**
   - Extract employers, dates, responsibilities, outcomes, metrics, tools,
     domains, seniority, education, awards, and public work.
   - Mark every claim as user-provided, source-supported, inferred, conflicting,
     or unknown.
   - Use only user-provided or source-supported claims in the final profile.
     Ask the user to confirm material conflicts.

4. **Interview in short rounds.**
   - Ask no more than five questions at a time.
   - Resolve identity and career facts before preferences.
   - Resolve target roles, adjacent roles, exclusions, geography,
     compensation, employment types, and company preferences before drafting.
   - Prefer concrete examples and outcomes over adjective-heavy summaries.

5. **Propose the search model.**
   - Present the search thesis and role families for confirmation.
   - Use `primary`, `adjacent`, and `edge` tiers deliberately.
   - Default thresholds to 80, 85, and 90 respectively. Change them only when
     the user supplies a clear reason.
   - Keep aliases specific enough to represent the same work. Do not group
     unrelated roles merely because they share a keyword.

6. **Generate the profile.**
   - Copy the asset template and replace every placeholder.
   - Preserve YAML types, indentation, and the canonical scoring keys.
   - Use factual evidence bullets: situation, personal action, observable
     result, and demonstrated capability.
   - Omit unknown facts instead of inserting `TODO`, guesses, or fabricated
     metrics.
   - Never place secrets, passwords, private contact details, government IDs,
     or financial account information in the profile.

7. **Validate and repair.**
   - Run:
     `python scripts/validate_profile.py /path/to/first-name-last-name.md`
   - The standalone validator requires PyYAML. If it is unavailable, install
     `pyyaml` in the isolated working environment or use Ferminator's validator.
   - Fix every error and rerun until it reports `VALID`.
   - If the Ferminator repository is available, also run:
     `ferminator profile validate /path/to/first-name-last-name.md`
   - Do not describe the file as complete if either available validator fails.

8. **Deliver.**
   - Provide the validated Markdown file.
   - Report source coverage, unresolved factual gaps, and any deliberately
     conservative search choices separately from the profile.
   - Do not silently revise confirmed facts during final formatting.

## Completion gate

Finish only when:

- the user has confirmed identity-sensitive sources;
- the search thesis and role families reflect the user's intent;
- scoring totals 100;
- thresholds and notification scores satisfy the profile contract;
- no placeholders remain;
- the validator reports `VALID`;
- unresolved gaps are disclosed outside the profile.
