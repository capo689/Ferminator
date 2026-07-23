# Creative Brief: Ferminator Career Intelligence Dashboard

## The idea

Ferminator is not another job board.

It is a personal career-intelligence system that continuously scans Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable, BambooHR, and company career sites—then identifies the opportunities most likely to move your career forward.

The dashboard should feel like stepping into a beautifully composed intelligence center built entirely around one person’s ambitions.

Not “Here are 12,000 jobs.”

Instead:

> “Here are the five opportunities that matter today—and exactly why.”

## The creative ambition

Create the most desirable job-search interface anyone has seen: cinematic enough to feel extraordinary, calm enough to use every morning, and intelligent enough to earn trust.

The reaction should be:

> “This understands me better than LinkedIn does.”

It should combine:

- The editorial confidence of Bloomberg and Monocle
- The refinement of Linear
- The warmth and clarity of Arc
- The data intelligence of Palantir—without its severity
- The momentum of a premium fitness dashboard
- The personal relevance of an excellent human career agent

The interface should make a stressful activity feel focused, optimistic, and under control.

## Positioning

**Ferminator is your private career radar.**

It searches across fragmented hiring systems, remembers what changed, understands your background, ranks opportunities by personal fit, and helps turn discoveries into applications.

Its core promise:

> Find the right opportunities earlier. Understand them faster. Pursue them better.

## Target user

An ambitious, experienced professional who:

- Has a multidisciplinary career that keyword filters struggle to understand
- Wants quality rather than an endless job feed
- Is pursuing several related role categories
- Needs help recognizing transferable fit
- Wants to monitor specific companies and market movements
- Values thoughtful guidance over automated noise
- Treats a job search as a strategic campaign

The initial design should feel personally built for Adam, while remaining extensible into a broader product.

## Emotional goals

The dashboard should make the user feel:

- Seen
- Ahead of the market
- Selective rather than desperate
- Energized rather than overwhelmed
- Informed rather than uncertain
- In command of a coherent campaign

Every morning, Ferminator should create a small sense of possibility.

## North-star experience

The user opens Ferminator and immediately sees:

> Good morning, Adam.  
> I found 14 new roles overnight. Three deserve your attention.

The first screen presents three exceptional matches—not a chart grid.

Each opportunity answers five questions immediately:

1. What is the role?
2. Why does it fit me?
3. What might disqualify it?
4. Why should I act now?
5. What should I do next?

Everything else supports that decision.

---

# Experience architecture

## Primary navigation

The product should have six focused spaces:

### Today

The daily career briefing.

- Best new matches
- Important changes to saved roles
- Application follow-ups
- Companies showing relevant hiring activity
- One recommended next action

### Discover

A unified search across every supported ATS.

- Natural-language search
- Advanced filters
- Semantic and exact matching
- Saved searches
- Map and list modes
- Match explanations

### Pipeline

A visual application workspace.

```text
Considering → Preparing → Applied → Interviewing → Offer
```

Each role retains notes, contacts, résumé version, correspondence, tasks, and history.

### Companies

Market and employer intelligence.

- Hiring momentum
- Relevant departments
- New role categories
- Compensation trends
- Geographic expansion
- Roles added and removed
- Company watchlists

### Intelligence

The analytical layer inherited from the original Ferminator.

- Hiring trends
- ATS coverage
- Department movements
- Compensation benchmarks
- Role-volume changes
- Market heat maps
- Skill-demand trends

### Profile

The model Ferminator uses to understand the user.

- Career history
- Skills and evidence
- Target roles
- Aspirations
- Constraints
- Compensation targets
- Location preferences
- Deal-breakers
- Search modes

---

# The “Today” dashboard

## Hero: the morning briefing

The top of the page should feel editorial, spacious, and personal.

Example:

> **Wednesday, July 22**  
> Good morning, Adam. The market moved in your direction overnight.

Supporting signals:

- 14 new matches
- 3 exceptional fits
- 2 saved roles changed
- 1 follow-up due today

A single luminous action:

**Review today’s briefing**

No giant navigation bar. No wall of metrics. No empty cards competing for attention.

## Opportunity constellation

The three strongest matches become the visual centerpiece.

The leading match is large and immersive:

> **Director, AI Enablement**  
> Airtable · Remote US  
> $185K–$240K · Posted 6 hours ago  
> **94% alignment**

Below the score:

- Strong leadership overlap
- Direct AI-adoption experience
- Excellent writing and enablement fit
- Compensation meets target
- One concern: enterprise SaaS experience preferred

Primary actions:

- Explore fit
- Save
- Prepare application
- Dismiss

Secondary matches appear as elegant adjacent cards, creating an intentional three-opportunity composition rather than a generic feed.

## Why this is here

Every recommendation should be explainable.

Selecting “Explore fit” opens a layered analysis:

```text
Your evidence                    Their requirement
────────────────────────────────────────────────────
AI systems implementation   →   Lead enterprise AI adoption
Enablement programs          →   Build internal learning systems
Executive communication     →   Influence senior stakeholders
Cross-functional operations →   Partner across product and GTM
```

Gaps should be equally honest:

```text
Potential gap
They prefer five years in enterprise SaaS.
Your adjacent agency and consulting work may compensate.
```

This could become Ferminator’s signature interaction.

## Market pulse

Below the daily matches, show a restrained horizontal signal strip:

- AI enablement roles: ↑ 18% this month
- Remote leadership roles: ↓ 7%
- Median relevant salary: $192K
- 11 watched companies are actively hiring

These should feel like market intelligence, not vanity metrics.

## Campaign focus

The dashboard ends with one recommended action:

> **Best use of 25 minutes:** Prepare your Airtable application while the role is under 12 hours old.

Buttons:

- Start preparation
- Choose another task

The product should reduce decision fatigue, not create more of it.

---

# Search and discovery

## Natural-language command bar

A beautiful universal search field should anchor Discover:

> “Find senior AI enablement or operations roles, remote or Los Angeles, above $170K, excluding quota-carrying sales.”

The interface translates the request into visible, editable filter chips.

This is essential: intelligence should feel magical, but never opaque.

## Results design

Avoid dense spreadsheet rows as the default.

Each result should show:

- Company logo and name
- Role title
- Location and work model
- Salary
- Posted/discovered time
- ATS source
- Match score
- Three strongest match reasons
- One potential concern
- Save, dismiss, compare, and prepare actions

A compact analytical view can remain available for power users.

## Freshness as a first-class signal

Job boards routinely obscure when Ferminator first observed a role. Make freshness visually meaningful:

- **Just surfaced**
- **New today**
- **3 days active**
- **Recently changed**
- **Reposted**
- **Possibly stale**

A subtle orbit or pulse around genuinely new high-match roles could become a recognizable visual motif.

---

# Visual direction

## Theme: Luminous intelligence

Not a black hacker dashboard. Not corporate blue SaaS. Not playful productivity software.

The world should feel like dawn breaking over a dark horizon: possibility emerging from complexity.

### Base palette

- Warm porcelain: `#F6F4EF`
- Ink: `#16181D`
- Midnight blue: `#172033`
- Atmospheric slate: `#687386`
- Electric iris: `#735CFF`
- Signal cyan: `#36C8D8`
- Opportunity gold: `#E7A93B`
- Positive green: `#46A878`
- Soft coral: `#E97867`

Use dark surfaces selectively—for immersive intelligence panels, command search, and high-impact moments—not as the entire interface.

## Light and dark modes

Light mode should be the emotional default: optimistic, editorial, and usable throughout the day.

Dark mode should feel cinematic and intentional, ideal for evening research—not merely an inversion.

## Typography

Use typography to communicate hierarchy and taste.

- Display: a distinctive editorial grotesk or restrained serif
- Interface: a precise contemporary sans-serif
- Data: tabular numerals with exceptional legibility

Large headlines should feel confident, not oversized for spectacle.

Job titles deserve typographic prominence. Metrics do not.

## Shape language

- Generous radii, but not bubbly
- Thin structural borders
- Soft, directional shadows
- Occasional glass-like overlays used sparingly
- Fine data lines and subtle atmospheric gradients
- Strong alignment and large zones of breathing room

Avoid the “every section is a rounded card” trap.

## Company identity

Company logos should create texture and recognition, but Ferminator’s visual system must remain dominant.

Use consistent logo containers and controlled color extraction so the interface never becomes visually chaotic.

---

# Signature interactions

## Career radar

A subtle radial visualization maps opportunities by:

- Personal fit
- Recency
- Career upside
- Application effort

The best opportunities pull toward the center.

This should be an optional exploratory view, not the primary navigation.

## Fit lens

Clicking a match score transforms the role card into a direct comparison between the opportunity and the user’s evidence.

The transition should feel like focusing a lens—not opening a generic modal.

## Time-travel timeline

Every job and company has a history:

- First detected
- Description changed
- Salary added
- Role removed
- Role reposted
- Application submitted
- Contact made

The timeline makes Ferminator’s historical dataset tangible and trustworthy.

## Opportunity compare

Select up to three roles and compare:

- Match
- Compensation
- Career upside
- Company momentum
- Work model
- Identified gaps
- Application effort
- Deadline urgency

The interface should help answer:

> Which opportunity deserves my energy?

## Momentum animation

When an application advances, the movement through the pipeline should feel satisfying but controlled—a fine streak of light, a gentle expansion, a moment of earned progress.

No confetti for routine actions. Celebration should feel adult.

---

# Data visualization

Charts must answer decisions, not merely display available data.

Good:

- Is demand for my target role increasing?
- Which companies are accelerating relevant hiring?
- What compensation range should I expect?
- Which skills appear most often in strong matches?
- Where am I losing momentum in my pipeline?

Avoid:

- Decorative pie charts
- Unlabeled sparklines
- Equal-weight KPI grids
- Visualizations that require explanation before they provide insight

Every chart should have an editorial conclusion:

> “AI enablement leadership openings have risen 23% across your watched companies in six weeks.”

---

# Empty states

Empty states should feel like guided momentum.

Instead of:

> No data yet.

Use:

> Your radar is warming up.  
> Add five companies or define your first search to begin discovering opportunities.

Include a clear action and a tasteful example of what will appear.

During initial ingestion:

> Scanning 428 career pages across eight hiring platforms.  
> We’ve indexed 31,204 roles so far.

This turns system activity into anticipation.

---

# Voice and copy

Ferminator’s voice is:

- Perceptive
- Calm
- Direct
- Encouraging without cheerleading
- Honest about uncertainty
- Never robotic
- Never desperate

Good:

> This is a strong adjacent fit. Your enablement experience maps well, but the role asks for deeper product-led growth exposure.

Bad:

> Congratulations! This amazing opportunity is perfect for you!

Ferminator should sound like a brilliant career strategist who respects the user’s judgment.

---

# Trust principles

For every match, clearly distinguish:

- Facts extracted from the job listing
- Facts drawn from the user’s profile
- Inferences made by Ferminator
- Unknown or missing information

Never fabricate:

- Salary
- Remote eligibility
- Required experience
- Company momentum
- Application status
- User qualifications

Scores should be decomposable and adjustable.

A 92% score must mean something.

---

# Responsive strategy

## Desktop

The complete intelligence workspace:

- Split views
- Comparison tools
- Rich filters
- Pipeline management
- Market analytics

## Mobile

A decisive daily companion:

- Today’s briefing
- Swipe through recommendations
- Save or dismiss
- Read fit analysis
- Complete follow-ups
- Receive alerts

Mobile should not attempt to compress the entire desktop dashboard.

---

# Accessibility

Jaw-dropping cannot come at the cost of usability.

Requirements:

- WCAG AA contrast minimum
- Full keyboard navigation
- Visible focus treatment
- Reduced-motion support
- Charts with textual summaries
- Color never used as the only signal
- Comfortable typography at default zoom
- Screen-reader explanations for match scores and trends

---

# What to avoid

- Hacker-terminal aesthetics
- A dashboard made entirely of cards
- Neon gradients everywhere
- Endless feeds
- Generic stock illustrations
- AI sparkle icons on every feature
- Gamifying application volume
- Pretending every match is excellent
- Dense recruiter-software tables as the default
- Making users configure 40 filters before seeing value
- Turning career anxiety into notification pressure

---

# Success criteria

The design succeeds if a user can:

- Understand their best opportunity within 10 seconds
- Understand why it matches within 30 seconds
- Start preparing an application within one minute
- Review new opportunities daily without feeling overwhelmed
- Trust why roles were ranked or excluded
- See meaningful career-market movement at a glance
- Manage the entire search without returning to a spreadsheet

The emotional success metric:

> Opening Ferminator makes the user feel that their career is moving—even before an application is submitted.

## Final creative statement

Ferminator should transform the internet’s fragmented, repetitive job listings into a living map of personal opportunity.

The product is not about searching harder.

It is about seeing the market clearly, recognizing the right moment, and acting with confidence.