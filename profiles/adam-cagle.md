---
schema_version: 1
profile:
  slug: adam-cagle
  display_name: Adam
  email_env: FERMINATOR_ADAM_EMAIL
search:
  enabled: true
  scan_interval_hours: 12
  default_geography:
    - Remote — United States
  allow_jobs_without_compensation: true
  compensation:
    currency: USD
    minimum_base_annual: null
  employment_types:
    - full-time
  target_seniority:
    - manager
    - senior-manager
    - director
    - lead
  target_titles:
    high:
      - AI Enablement
      - AI Operations
      - Marketing AI Operations
      - AI Adoption
      - Knowledge Operations
    adjacent:
      - Developer Advocacy
      - Technical Content
      - Enablement
      - Knowledge Management
      - Content Operations
      - Prompt Engineering
  required_any: []
  preferred:
    - enterprise AI adoption
    - cross-functional operations
    - technical writing
    - enablement programs
    - executive communication
    - workflow design
    - knowledge systems
  exclude:
    phrases:
      - quota-carrying
      - commission only
      - unpaid
    title_phrases:
      - Account Executive
      - Sales Development Representative
notifications:
  dashboard: true
  email: true
  minimum_score: 70
  exceptional_score: 88
  max_daily_matches: 12
scoring:
  role_alignment: 30
  career_evidence: 20
  skills: 15
  seniority: 10
  geography: 10
  compensation: 5
  company_preference: 5
  freshness: 5
---

# Adam Cagle — Career Search Profile

This file is the source of truth for Adam's Ferminator search. Concrete claims,
employers, dates, outcomes, portfolio links, and complete résumé evidence should
be added before match-quality evaluation. Do not include passwords, government
identifiers, financial information, or other secrets.

## Search thesis

Find roles where AI systems, enablement, operations, communication, and
organizational adoption overlap. Favor opportunities where a multidisciplinary
operator can translate complex technology into useful workflows, learning
systems, content, and measurable behavior change.

## Strong-fit themes

- AI enablement and adoption
- AI operations and workflow implementation
- Cross-functional program leadership
- Technical communication and education
- Knowledge systems and content operations
- Enterprise change and stakeholder enablement
- Building repeatable systems from ambiguous requirements

## Career evidence

Add evidence as short, factual bullets. Each bullet should describe:

1. the situation or problem,
2. the action Adam personally took,
3. the measurable or observable result,
4. the skills demonstrated.

### AI systems and operations

- TODO: Add verified projects, scope, tools, users, and outcomes.

### Enablement and education

- TODO: Add verified programs, audiences, assets, adoption, and outcomes.

### Leadership and cross-functional work

- TODO: Add verified teams, stakeholders, decisions, and outcomes.

### Writing, content, and communication

- TODO: Add verified content types, audiences, channels, and outcomes.

### Technical implementation

- TODO: Add verified platforms, integrations, automation, and outcomes.

## Constraints

- Remote United States is the default.
- The YAML front matter may add accepted locations or relocation rules.
- Compensation rules belong in YAML so they are enforced consistently.
- Jobs missing compensation remain eligible but receive no compensation bonus.

## Company preferences

### Prioritize

- TODO: Add companies or company characteristics.

### Avoid

- TODO: Add companies or characteristics only when a real exclusion exists.

## Match calibration

Add labeled examples after the first ingestion:

- Excellent match:
- Good adjacent match:
- Superficial keyword match:
- Definite rejection:

