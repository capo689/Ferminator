# FINISHER Scorecard

**FINISHER Score: 36.6 / 100** -- **DO NOT LAUNCH**  (+3.5 vs previous run)

- Uncapped weighted score: 36.6
- **Capped at 39**: 16 P0 blocker(s) open
- Assessment coverage: 100.0% (130/130 applicable checks assessed)
- Open blockers: P0 16 | P1 54 | P2 24

## Domain scores

| Domain | Score | | Wt | Checks | Open P0 | Open P1 |
|---|---:|---|---:|---:|---:|---:|
| D01 Identity, Auth & Authorization | 21.7 | `####................` | 12 | 13 | 5 | 6 |
| D02 Secrets & Key Management | 41.0 | `########............` | 8 | 7 | 1 | 4 |
| D03 Data Layer, Migrations & Backups | 36.9 | `#######.............` | 9 | 11 | 4 | 3 |
| D04 API & Backend Correctness | 69.6 | `##############......` | 7 | 9 | 0 | 1 |
| D05 Frontend, UX & Accessibility | 17.4 | `###.................` | 6 | 8 | 0 | 6 |
| D06 Application Security | 44.4 | `#########...........` | 9 | 12 | 0 | 5 |
| D07 Supply Chain & Dependency Integrity | 46.0 | `#########...........` | 6 | 9 | 1 | 2 |
| D08 CI/CD & Release Engineering | 55.0 | `###########.........` | 6 | 8 | 0 | 2 |
| D09 Environments, Config & Infrastructure | 41.7 | `########............` | 5 | 6 | 1 | 2 |
| D10 Observability & Error Tracking | 29.6 | `######..............` | 7 | 8 | 1 | 4 |
| D11 Reliability, Backup & Incident Response | 20.0 | `####................` | 7 | 7 | 0 | 4 |
| D12 Performance, Caching & Scale | 48.8 | `##########..........` | 5 | 7 | 0 | 1 |
| D13 Cost Control & Abuse Prevention | 22.9 | `#####...............` | 5 | 4 | 0 | 2 |
| D15 Privacy, Legal & Compliance | 20.8 | `####................` | 6 | 6 | 2 | 3 |
| D16 Testing & Verification | 29.5 | `######..............` | 6 | 7 | 1 | 4 |
| D18 Documentation & Handoff | 50.0 | `##########..........` | 4 | 4 | 0 | 3 |
| D19 Product Truth & Outcome Measurement | 41.7 | `########............` | 3 | 4 | 0 | 2 |

## P0 -- blocks any launch (16 open)

| ID | Check | Now | Needed |
|---|---|---:|---:|
| AUTH-01 | Authentication uses a battle-tested provider or framework, not hand-rolled code | 1 (CLAIMED) | 3 |
| AUTHZ-01 | Every resource access checks ownership, not just authentication | 1 (CLAIMED) | 3 |
| AUTHZ-02 | Tenant isolation is enforced at the database layer, not only in application code | 1 (CLAIMED) | 3 |
| AUTH-03 | Sessions expire, logout truly invalidates, and session IDs rotate on privilege change | 0 (ABSENT) | 3 |
| AUTH-05 | Password reset and email verification tokens are single-use, short-lived, and unguessable | 0 (ABSENT) | 3 |
| SEC-02 | Secret scan of the full git history passes, and anything ever exposed has been rotated | 2 (IMPLEMENTED) | 3 |
| DATA-01 | Automated backups exist for every production datastore | 1 (CLAIMED) | 3 |
| DATA-02 | A restore has actually been performed and the result verified | 2 (IMPLEMENTED) | 3 |
| DATA-03 | Production, staging, and development use separate datastores | 0 (ABSENT) | 3 |
| DATA-04 | No human or agent has standing write access to the production database | 0 (ABSENT) | 3 |
| SUP-01 | Install scripts do not run for arbitrary transitive dependencies | 1 (CLAIMED) | 3 |
| ENV-01 | Development, staging, and production are genuinely separate | 0 (ABSENT) | 3 |
| OBS-01 | Error tracking is installed on both frontend and backend and receives production errors | 0 (ABSENT) | 3 |
| LEG-01 | A privacy policy and terms of service are published and accurate | 0 (ABSENT) | 3 |
| LEG-02 | A data inventory exists: what you collect, where it lives, who it goes to | 2 (IMPLEMENTED) | 3 |
| TEST-01 | Automated tests cover authorization on every endpoint | 0 (ABSENT) | 3 |

## P1 -- blocks paid or public launch (54 open)

| ID | Check | Now | Needed |
|---|---|---:|---:|
| AUTHZ-04 | Authorization model is written down and matches the code | 2 (IMPLEMENTED) | 3 |
| AUTH-04 | Session cookies use Secure, HttpOnly, SameSite, and the __Host- prefix where possible | 0 (ABSENT) | 3 |
| AUTH-06 | Login, reset, signup, and OTP endpoints are rate limited per account and per IP | 0 (ABSENT) | 3 |
| AUTH-07 | Password policy follows current guidance: length over composition, breach-list blocking | 1 (CLAIMED) | 3 |
| AUTH-10 | Tokens are validated with a pinned algorithm and are revocable | 0 (ABSENT) | 3 |
| AUTH-11 | Account deletion and data export exist and actually work end to end | 1 (CLAIMED) | 3 |
| SEC-03 | Secrets live in a secret manager or platform env store, scoped per environment | 2 (IMPLEMENTED) | 3 |
| SEC-04 | CI/CD uses short-lived federated credentials (OIDC), not long-lived cloud keys | 0 (ABSENT) | 3 |
| SEC-05 | Service accounts and database credentials follow least privilege | 0 (ABSENT) | 3 |
| SEC-06 | Secrets never appear in logs, error messages, traces, screenshots, or AI prompts | 2 (IMPLEMENTED) | 3 |
| DATA-06 | Migrations are linted for locking and destructive operations | 0 (ABSENT) | 3 |
| DATA-07 | Rollback strategy for schema changes is defined and it is roll-forward-safe | 2 (IMPLEMENTED) | 3 |
| DATA-10 | Data retention and deletion rules are defined per data class | 2 (IMPLEMENTED) | 3 |
| API-02 | Every input is validated against a schema at the trust boundary, at runtime | 2 (IMPLEMENTED) | 3 |
| FE-01 | Every async surface has loading, error, empty, and success states | 1 (CLAIMED) | 3 |
| FE-02 | Error boundaries prevent one component failure from blanking the app | 1 (CLAIMED) | 3 |
| FE-03 | Core flows verified on real mobile devices, Safari, and a throttled network | 1 (CLAIMED) | 3 |
| FE-04 | Forms survive hostile and messy input | 2 (IMPLEMENTED) | 3 |
| FE-05 | Automated accessibility scan passes on core pages | 0 (ABSENT) | 3 |
| FE-06 | Keyboard-only and screen-reader passes completed on critical journeys | 0 (ABSENT) | 3 |
| APPSEC-05 | CSRF protection is present on state-changing requests | 2 (IMPLEMENTED) | 3 |
| APPSEC-06 | SAST runs on pull requests and blocks new high/critical findings | 1 (CLAIMED) | 3 |
| APPSEC-08 | A DAST baseline scan has been run against staging and findings triaged | 0 (ABSENT) | 3 |
| APPSEC-09 | Manual authorization tampering has been attempted and failed | 0 (ABSENT) | 3 |
| SUP-03 | A dependency cooldown / minimum release age is configured | 0 (ABSENT) | 3 |
| SUP-05 | Every dependency actually exists and was not hallucinated | 2 (IMPLEMENTED) | 3 |
| CI-04 | CODEOWNERS protects auth, payments, migrations, and CI workflow paths | 0 (ABSENT) | 3 |
| CI-06 | Changes are previewable before production | 0 (ABSENT) | 3 |
| ENV-04 | TLS everywhere, HTTP redirects to HTTPS, and certificate renewal is automated | 2 (IMPLEMENTED) | 3 |
| ENV-05 | Serverless and platform timeouts are known and no core action exceeds them | 2 (IMPLEMENTED) | 3 |
| OBS-03 | Logs redact secrets and personal data and have a defined retention period | 2 (IMPLEMENTED) | 3 |
| OBS-04 | Alerts exist for the failures that matter, and they reach a human | 2 (IMPLEMENTED) | 3 |
| OBS-05 | Uptime and synthetic monitoring check the real user journey, not just a 200 | 2 (IMPLEMENTED) | 3 |
| REL-01 | RTO and RPO are defined, written down, and consistent with the backup configuration | 0 (ABSENT) | 3 |
| REL-02 | An incident runbook exists covering the realistic failure set | 2 (IMPLEMENTED) | 3 |
| REL-03 | Someone is on call, or there is an explicit documented decision that nobody is | 0 (ABSENT) | 3 |
| REL-04 | A breach and data-exposure response plan exists with notification timelines | 2 (IMPLEMENTED) | 3 |
| PERF-03 | Static assets are served from a CDN with correct cache headers | 2 (IMPLEMENTED) | 3 |
| COST-03 | Rate limiting exists on all public and expensive endpoints | 0 (ABSENT) | 3 |
| COST-05 | Abuse paths have been tested: signup spam, scraping, resource exhaustion | 0 (ABSENT) | 3 |
| LEG-03 | Data subject rights are actually operable: access, deletion, correction, export | 1 (CLAIMED) | 3 |
| LEG-05 | US state privacy obligations are handled, including universal opt-out signals | 0 (ABSENT) | 3 |
| TEST-02 | The critical user journeys have end-to-end tests | 2 (IMPLEMENTED) | 3 |
| TEST-04 | Tests actually assert; coverage is measured on the diff, not chased globally | 2 (IMPLEMENTED) | 3 |
| TEST-05 | The API has been fuzzed against its schema | 0 (ABSENT) | 3 |
| TEST-06 | Tests run against a real database, not mocks, for data-layer behavior | 2 (IMPLEMENTED) | 3 |
| DOC-01 | README lets a new developer run the project locally from zero | 2 (IMPLEMENTED) | 3 |
| DOC-02 | Architecture notes exist: system diagram, data model, vendor map, auth model | 2 (IMPLEMENTED) | 3 |
| DOC-03 | Deploy and rollback procedures are written down and executable by someone else | 2 (IMPLEMENTED) | 3 |
| PROD-01 | The problem, the user, and the success metric are written down in one paragraph | 2 (IMPLEMENTED) | 3 |
| PROD-02 | A baseline was captured before changes so improvement is provable | 2 (IMPLEMENTED) | 3 |
| EMAIL-01 | Sending domain is authenticated with SPF, DKIM, and an enforcing DMARC policy | 0 (ABSENT) | 3 |
| EMAIL-04 | Bounces, complaints, and suppressions are processed and monitored | 0 (ABSENT) | 3 |
| EMAIL-05 | Marketing mail is separated from transactional, carries an honest unsubscribe, and honours it immediately | 2 (IMPLEMENTED) | 3 |

## P2 -- blocks scale (24 open)

| ID | Check | Now | Needed |
|---|---|---:|---:|
| AUTH-09 | OAuth/OIDC integrations use PKCE, exact redirect URI matching, and state/nonce binding | 0 (ABSENT) | 2 |
| SEC-07 | Key rotation is documented, rehearsed, and possible without downtime | 1 (CLAIMED) | 2 |
| DATA-11 | Sensitive fields are encrypted at rest beyond disk-level encryption where warranted | 1 (CLAIMED) | 2 |
| FE-07 | Core Web Vitals measured on real users and within thresholds | 0 (ABSENT) | 2 |
| FE-08 | Five target users complete the core flow unaided | 0 (ABSENT) | 2 |
| APPSEC-11 | A vulnerability disclosure path exists | 0 (ABSENT) | 2 |
| SUP-06 | GitHub Actions are pinned to full commit SHAs | 0 (ABSENT) | 2 |
| SUP-07 | CI workflow token permissions are least-privilege and untrusted input is never interpolated into shell | 1 (CLAIMED) | 2 |
| SUP-09 | Published artifacts carry build provenance | 0 (ABSENT) | 2 |
| CI-08 | Risky changes ship behind feature flags with a kill switch | 0 (ABSENT) | 2 |
| CI-09 | Post-deploy verification watches error rate, latency, and key funnels | 1 (CLAIMED) | 2 |
| ENV-06 | DNS, domains, and registrar access are documented and secured | 0 (ABSENT) | 2 |
| OBS-06 | Distributed tracing covers the slow and complex paths | 0 (ABSENT) | 2 |
| OBS-07 | Product analytics track the core funnel | 0 (ABSENT) | 2 |
| REL-05 | Incidents get blameless post-mortems and produce concrete follow-up actions | 0 (ABSENT) | 2 |
| REL-06 | There is a way to tell customers what is happening | 0 (ABSENT) | 2 |
| REL-07 | Third-party outage behavior is defined and degraded mode is tested | 1 (CLAIMED) | 2 |
| PERF-05 | A load test has been run at a realistic launch multiple and the breaking point is known | 0 (ABSENT) | 2 |
| PERF-06 | Expensive repeated work is cached with a defined invalidation strategy | 0 (ABSENT) | 2 |
| PERF-07 | A scaling plan exists for the next order of magnitude | 1 (CLAIMED) | 2 |
| COST-07 | Infrastructure spend is forecast for the next 90 days at expected growth | 1 (CLAIMED) | 2 |
| LEG-09 | Accessibility obligations have been assessed for your markets | 0 (ABSENT) | 2 |
| TEST-08 | A human has read the security-critical code, not just the tests | 1 (CLAIMED) | 2 |
| PROD-04 | There is a way for users to report problems and it is monitored | 0 (ABSENT) | 2 |
