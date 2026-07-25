# ADR: Deterministic retrieval and matching for V1

Date: 2026-07-23  
Status: Accepted

## Context

The product needs excellent, explainable matching but will not use an AI API
key initially.

## Decision

Use PostgreSQL full-text retrieval plus a weighted rule engine. Separate hard
eligibility from ranking. Store every component, evidence match, concern, and
penalty with the result.

## Alternatives considered

- Hosted embeddings and LLM reranking: stronger semantic matching in some cases,
  but introduces cost, secrets, model drift, and opaque scoring.
- Keyword search alone: simple but produces weak recall and poor prioritization.
- Local embedding model on Render: higher memory/build cost and operational
  complexity for the alpha.

## Consequences

- Profiles need rich synonyms, adjacent titles, evidence phrases, and explicit
  exclusions.
- Match quality is measurable and reproducible.
- A labeled evaluation set is required before beta.
- An optional semantic reranker can be added behind the same interface later.

## Reversal plan

Keep candidate retrieval and final ranking behind interfaces. Add local or
hosted semantic ranking as another component without replacing eligibility.

