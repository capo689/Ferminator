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
  default_zip: "97702"
  default_radius_miles: 50
  default_location_mode: remote_or_near
  allow_jobs_without_compensation: true
  compensation:
    currency: USD
    minimum_base_annual: 100000
  employment_types:
    - full-time
    - contract
    - contract-to-hire
  target_seniority:
    - manager
    - senior-manager
    - director
    - lead
  target_titles:
    high: []
    adjacent: []
  role_families:
    - id: ai-enablement
      label: AI Enablement & Adoption
      tier: primary
      threshold: 80
      description: Helping teams understand, adopt, govern, and use AI successfully.
      aliases:
        - AI Enablement
        - Generative AI Enablement
        - AI Adoption
        - AI Education
        - AI Customer Education
    - id: ai-transformation-operations
      label: AI Transformation & Operations
      tier: primary
      threshold: 80
      description: Operationalizing AI programs, workflows, governance, and implementation.
      aliases:
        - AI Transformation
        - AI Operations
        - Generative AI Operations
        - AI Program
        - AI Implementation
        - AI Solutions
        - Applied AI
        - AI Governance
        - AI Innovation
        - AI Product Operations
        - Marketing AI Operations
        - AI Workflow Automation
        - AI Automation
        - LLM Operations
    - id: ai-content-systems
      label: AI Content Systems
      tier: primary
      threshold: 80
      description: Building governed AI systems for content, voice, and knowledge.
      aliases:
        - AI Content Systems
        - AI Content Operations
        - AI Content Strategy
        - AI Content Design
        - Knowledge Operations
        - Brand Voice AI
    - id: creative-ai-technology
      label: Creative AI & Technology
      tier: primary
      threshold: 80
      description: Hands-on creative technology, agents, and applied AI solutions.
      aliases:
        - AI Marketing Engineer
        - Creative Technologist
        - Creative AI
        - AI Creative
        - Agent Architect
        - Agentic AI
        - Applied AI Consultant
    - id: copywriting
      label: Copywriting
      tier: primary
      threshold: 65
      description: Senior, hands-on copywriting across advertising, brand, digital, and direct response.
      aliases:
        - Copywriter
        - Senior Copywriter
        - Lead Copywriter
        - Advertising Copywriter
        - Agency Copywriter
        - Brand Copywriter
        - Marketing Copywriter
        - Creative Copywriter
        - Digital Copywriter
        - Web Copywriter
        - Website Copywriter
        - B2B Copywriter
        - B2C Copywriter
        - Direct Response Copywriter
        - Technical Copywriter
        - UX Copywriter
        - Product Copywriter
        - Content Copywriter
        - SEO Copywriter
        - Email Copywriter
        - Ecommerce Copywriter
        - E-commerce Copywriter
        - Social Copywriter
        - Freelance Copywriter
        - Contract Copywriter
        - AI Copywriter
        - Copy Lead
        - Copy Supervisor
        - Group Copy Supervisor
    - id: creative-direction-copy
      label: Copy & Creative Direction
      tier: adjacent
      threshold: 75
      description: Copy-led creative direction and senior creative team leadership.
      aliases:
        - Associate Creative Director Copy
        - Associate Creative Director, Copy
        - ACD Copy
        - Creative Director Copy
        - Creative Director, Copy
        - Group Creative Director Copy
        - Executive Creative Director Copy
        - Head of Copy
        - VP Copy
    - id: content-strategy-brand
      label: Content & Brand Strategy
      tier: adjacent
      threshold: 75
      description: Brand voice, messaging, editorial direction, and content strategy.
      aliases:
        - Content Strategy
        - Content Strategist
        - Senior Content Strategist
        - Content Director
        - Director of Content
        - Editorial Director
        - Brand Strategist
        - Brand Strategy
        - Messaging Strategist
        - Brand Voice
        - Product Narrative
    - id: technical-content-education
      label: Technical Content & Education
      tier: adjacent
      threshold: 80
      description: Translating technical products into useful education and content.
      aliases:
        - Technical Content
        - Technical Writer AI
        - Technical Writer, AI
        - AI Technical Writer
        - Developer Education
        - Developer Advocacy
        - Developer Relations
        - Customer Education
    - id: ai-search
      label: AI Search & Discoverability
      tier: primary
      threshold: 80
      description: AI search, AEO, GEO, and modern organic discoverability.
      aliases:
        - AI Search Strategist
        - AI SEO
        - AEO Strategist
        - GEO Strategist
        - Generative Engine Optimization
        - Answer Engine Optimization
    - id: conversation-prompt-design
      label: Conversation & Prompt Design
      tier: primary
      threshold: 80
      description: Designing useful, safe conversational and prompt-driven experiences.
      aliases:
        - Conversation Design
        - Conversation Designer
        - Prompt Design
        - Prompt Designer
        - Prompt Engineering
        - Prompt Engineer
    - id: content-creative-operations
      label: Content & Creative Operations
      tier: adjacent
      threshold: 75
      description: Systems, workflows, and governance for content and creative teams.
      aliases:
        - Content Operations
        - Creative Operations
        - Knowledge Management
        - Content Design
        - Content Designer
    - id: consulting-transformation
      label: AI & Digital Consulting
      tier: adjacent
      threshold: 85
      description: Client-facing implementation and transformation work with strong AI relevance.
      aliases:
        - AI Implementation Consultant
        - AI Solutions Consultant
        - Digital Transformation Consultant
        - Generative AI Consultant
    - id: product-marketing-narrative
      label: Product Marketing & Narrative
      tier: edge
      threshold: 90
      description: Product positioning and narrative roles that require unusually strong fit.
      aliases:
        - Product Marketing Manager
        - Product Marketing Director
        - Director of Product Marketing
        - Product Marketing Lead
        - Product Narrative Lead
        - Go-to-Market Narrative
    - id: agency-creative-leadership
      label: Agency & Creative Leadership
      tier: edge
      threshold: 90
      description: Broad creative leadership roles shown only when the evidence is exceptional.
      aliases:
        - Head of Creative
        - VP Creative
        - Creative Operations Director
        - Integrated Creative Director
        - Campaign Strategist
        - Creative Strategist
  require_title_match: true
  enforce_default_geography: true
  adjacent_minimum_preferred_hits: 1
  required_any: []
  preferred:
    - enterprise AI adoption
    - cross-functional operations
    - technical writing
    - enablement programs
    - executive communication
    - workflow design
    - knowledge systems
    - brand voice
    - content systems
    - human approval
    - guardrails
    - AI agents
    - MCP
    - RAG
    - APIs
    - workflow automation
    - creative technology
    - AI search
  exclude:
    phrases:
      - quota-carrying
      - commission only
      - unpaid
      - commission only
      - data annotation
      - active security clearance
      - 50% travel
    title_phrases:
      - Account Executive
      - Account Director
      - Sales Development Representative
      - Sales Enablement
      - Revenue Enablement
      - Customer Success Enablement
      - Customer Enablement
      - Field Enablement
      - Partner Enablement
      - Procurement Enablement
      - Partner Development
      - Public Relations
      - PR Director
      - Security
      - Compensation Operations
      - Travel Operations
      - Machine Learning Engineer
      - Data Scientist
      - Research Scientist
      - MLOps Engineer
      - Backend Engineer
      - Software Engineer
      - Forward Deployed Engineer
      - Applied AI Engineer
      - AI Enablement Engineer
      - Agentic AI Engineer
      - Salesforce Administrator
notifications:
  dashboard: true
  email: true
  review_minimum_score: 58
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

Find the rare roles where Adam's two careers reinforce one another: twenty-five
years of senior copywriting, brand voice, creative leadership, and agency
operations combined with hands-on applied-AI product, workflow, agent, and
enablement building. Favor the writer-builder intersection over generic
creative leadership or generic AI strategy.

## Strong-fit themes

- AI copywriting, brand voice, and governed content systems
- Hands-on AI enablement, adoption, workflows, and internal tools
- AI agents, MCP, RAG, APIs, evaluations, guardrails, and human approval
- AI search, AEO, GEO, SEO, and technical content
- Creative technology and AI-assisted production
- Client discovery, proposals, implementation, and delivery
- Building repeatable systems from ambiguous business requirements

## Career evidence

Add evidence as short, factual bullets. Each bullet should describe:

1. the situation or problem,
2. the action Adam personally took,
3. the measurable or observable result,
4. the skills demonstrated.

### AI systems and operations

- Founder and AI Agent Architect at Agentic689 since 2024; owns product
  direction, architecture, prompts, governance, interfaces, testing,
  deployment, and iteration.
- Built Singularity SEO, a production AI-managed WordPress SEO/AEO/GEO system
  using authenticated MCP, REST APIs, webhooks, Search Console, retrieval,
  governed proposals, human approval, and rollback-ready history.
- Built Agent Exchange, a live public beta using Node.js, PostgreSQL, Supabase,
  identity verification, rate limits, permissions, lifecycle controls, and
  audit records.
- Built BookLite and VRT2 as open-source, human-governed AI systems; VRT2's
  paid test contributed to a technology investment fund purchasing ten Single
  Stock Agents.

### Enablement and education

- Built Agency689 Writing Systems for daily client use with brand-context
  retrieval, voice governance, multi-draft generation, standards review, and
  human approval; reduced first-draft time by roughly half.
- Creates reusable prompt and agent libraries, playbooks, governance
  documentation, and direct guidance that move wary users into routine use.

### Leadership and cross-functional work

- Co-founded and has operated Agency689 since 2001 across more than sixty
  accounts, leading discovery, proposals, scoping, budgets, staffing, vendors,
  production, delivery, and teams up to fifteen.
- Led long-running relationships with founders, owners, boards, C-suite
  leaders, marketing teams, creatives, developers, and production partners.

### Writing, content, and communication

- Award-winning lead copywriter and creative leader with Webby, Ad Club, and
  Netty recognition; writes brand voice, campaigns, websites, email, product
  narratives, white papers, architecture explainers, and governance material.
- Sunset Marquis email program produces approximately $150,000 per month in
  attributed revenue; Traveler Guitar DTC grew from about $1.1M to $5M.

### Technical implementation

- Ships with Python, FastAPI, JavaScript, TypeScript, Node.js, SQL, PostgreSQL,
  Supabase, Docker, Vercel, Render, Cloudflare, OAuth, webhooks, n8n, Zapier,
  LLM APIs, LangGraph, MCP/FastMCP, RAG, and Qdrant.
- Does not claim Kubernetes, MLOps, large-cloud infrastructure ownership,
  formal ML engineering, formal PMO leadership, or a four-year degree.

## Constraints

- Remote United States is the default.
- The YAML front matter may add accepted locations or relocation rules.
- Full-time base floor is $100,000; $90,000–$99,999 requires manual review.
- Jobs missing compensation remain eligible but receive no compensation bonus.
- Ordinary hybrid/on-site work is Bend/Redmond only. West Coast or Salt Lake
  City exceptions require at least $150,000 base and no more than 25% on-site.
- More than 25% travel is normally a rejection.

## Company preferences

### Prioritize

- AI-native product companies, Anthropic partners, agent platforms, applied-AI
  consultancies, martech, adtech, content and creative technology, AI search,
  hospitality/travel technology, fintech, gaming, and creator tools.

### Avoid

- Fake or unverifiable employers, expert networks presented as employment,
  commission-only sales, data-labeling/evaluator marketplaces, content farms,
  and anonymous staffing listings without employer and compensation.

## Match calibration

Add labeled examples after the first ingestion:

- Excellent match:
- Good adjacent match:
- Superficial keyword match:
- Definite rejection:
