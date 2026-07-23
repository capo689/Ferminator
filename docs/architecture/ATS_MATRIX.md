# ATS Support Matrix

Validated: 2026-07-23

## V1: public structured sources

| Provider | Public contract | Authentication | Live validation | V1 decision |
|---|---|---|---|---|
| Greenhouse | `GET /v1/boards/{token}/jobs?content=true` | None | 413 jobs from Anthropic | Build |
| Lever | `GET /v0/postings/{site}?mode=json` | None | 388 jobs from Lever demo | Build |
| Ashby | `GET /posting-api/job-board/{name}` | None | 737 jobs from OpenAI | Build |
| SmartRecruiters | `GET /v1/companies/{id}/postings` | None | 8 jobs from SmartRecruiters | Build |
| Workable | `GET /api/accounts/{subdomain}?details=true` | None | 5 jobs from Ometria | Build |
| BambooHR | `GET /careers/list`, then `/careers/{id}/detail` | None | 5 jobs from G2 | Build with contract monitor |

The live counts are observations, not test assertions. Contract tests assert
shape using committed redacted fixtures; optional smoke tests validate live
endpoints without making CI depend on third-party uptime.

## V2: isolated experimental adapters

| Provider | Reason deferred | Entry criteria |
|---|---|---|
| Workday | Undocumented tenant/site-specific POST contract and result cap | Two stable tenant fixtures, pagination tests, legal review, circuit breaker |
| Custom career sites | HTML and JavaScript extraction varies by company | Explicit allowlist, robots/terms review, JSON-LD first, extraction health metrics |
| iCIMS | Site variants and HTML-heavy search | Stable public feed proof across representative tenants |
| JazzHR | HTML/JSON-LD extraction | Contract fixtures and respectful throttling |
| Recruitee | Not required for initial scope | Public API validation and registry demand |
| Personio | XML normalization work | XML security and pagination tests |
| Teamtailor | Public site behavior varies | Contract validation and demand |
| Rippling | Board-specific behavior | Public contract validation |

## Adapter contract

Every V1 adapter must implement:

```python
class ATSAdapter(Protocol):
    provider: ATSProvider

    def validate_board(self, board: BoardRef) -> BoardValidation: ...
    def fetch_jobs(self, board: BoardRef) -> list[RawJob]: ...
    def normalize(self, board: BoardRef, raw: RawJob) -> NormalizedJob: ...
```

Every normalized job includes:

- provider and board identifier
- provider job ID and globally stable source key
- company
- title
- description text and sanitized HTML
- department/team
- employment type and seniority when available
- workplace type
- primary and secondary locations
- compensation range, currency, and interval
- published and updated timestamps
- job and application URLs
- source payload hash and retrieval timestamp

## Provider safeguards

- Per-host concurrency and request-rate limits
- Timeouts and bounded retries
- `Retry-After` support
- Maximum response size and job count
- HTML sanitization
- Schema drift alerts
- Circuit breaker after repeated contract failures
- User-Agent identifying Ferminator and a contact URL before public rollout
- No authenticated, internal, or candidate APIs
- No automated application submission

