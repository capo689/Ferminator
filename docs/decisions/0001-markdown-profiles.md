# ADR: Named Markdown profiles as search source of truth

Date: 2026-07-23  
Status: Accepted

## Context

The alpha supports up to five people and must deliver strong matches without an
AI API key. Search intent and career evidence need to be human-readable,
reviewable, versioned, and easy to refine.

## Decision

Store one named profile at `profiles/<person-slug>.md`. Use YAML front matter
for validated controls and Markdown sections for career evidence. Parse each
commit into a versioned database profile used by deterministic retrieval and
scoring.

## Alternatives considered

- Database-only forms: easier UI editing, weaker review/version history.
- JSON/YAML only: machine-friendly, poor for nuanced evidence.
- Vector database plus LLM: higher semantic recall but introduces keys, cost,
  nondeterminism, and privacy considerations.

## Consequences

- Profile edits are reviewable and reversible in Git.
- Matching can explain exactly which profile rule or evidence matched.
- A schema validator and preview command are required.
- Browser-based editing is deferred until safe round-trip editing is designed.

## Reversal plan

Persist the parsed profile model independently from Markdown syntax. A future
editor or AI index can write the same model without changing matching tables.

