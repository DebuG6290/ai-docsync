# v0.3 team beta: release evidence

Prepared on 2 November 2026 from `33aed9c2561aaac7efb680f24e04ee7b4e790063`.

## Delivered milestone

- A credential-free, session-isolated offline sample, launched by `docsync-demo` or deployed separately through `demo_app.py`. Scripted suggestions/merges are labelled. Real immutable proposal versions, explicit approval and knowledge activation are exercised.
- Native OIDC sign-in for the supported team workspace. Exact issuer/subject invitations, explicit reader/reviewer/admin permissions, repository ID/name validation, token expiry and maximum eight-hour token age. A legacy session-state login flag cannot bypass OIDC. Shared passwords are local development only.
- Database-backed user/repository usage allowances, atomic under parallel requests, with burst bounds and input limits. UI audit records carry actor identities. This is not a monetary/token cap.
- Validated remote Git inputs, bounded Git calls, sanitized remote errors, disabled Git hooks/file/ext protocols/text conversion. Provider redirects are rejected and model response bodies are bounded without changing reasoning prompts or schemas.
- Safe configuration preflight, documented data flow/retention/trust boundaries, exact dependency pins, automated dependency/static scans, loopback-only development Compose exposure and a non-root container definition.
- README quickstart, hosted migration guidance, security policy and MIT license.

## Completed checks in the development workspace

| Check | Result |
| --- | --- |
| Existing baseline before changes | 200 passed, 2 PostgreSQL tests skipped |
| Final Python 3.12 test suite | 238 passed, 3 PostgreSQL tests skipped (including the new PostgreSQL concurrency check) |
| GitHub Actions with PostgreSQL/pgvector | Functional release commit `4d5ca42`: all 241 tests passed; dependency audit and static checks passed in run 41442387381 |
| New regression scope | OIDC claim/expiry/invitation checks; forged legacy login; reader service/UI denial; cross-repo read/mutation bounds; actor audit; concurrent allowance enforcement; secret-safe preflight; additive usage migration; bounded provider response; sample edit/approve/activate/reset and session isolation |
| Real UI interactions through Streamlit AppTest | Login, repository switching, every existing page, review/edit/approval, reader role and offline sample lifecycle passed |
| Pinned dependency audit | pip-audit 2.10.1: 98 entries, zero skipped, no known vulnerabilities reported |
| Static security threshold | Bandit 1.9.4: no unsuppressed medium/high findings. One reviewed B608 false positive in the existing SQLite store is annotated: only `?` placeholders are interpolated and values are bound. Low-level subprocess/assert notices remain subject to code review. |
| Install path | `pip install --dry-run -r requirements.txt` resolved successfully; actual installation through the same requirements/constraints succeeded with uv |
| Compilation and diff formatting | Passed |

Known test warning: the installed FastAPI/Starlette TestClient emits an httpx deprecation warning. It does not fail the suite.

## Not established by these checks

- PostgreSQL-specific runtime tests were skipped locally because no PostgreSQL/pgvector service is available here. They passed in GitHub CI, including the concurrent operation allowance test. CI provisions an ephemeral service; this does not establish the health of the deployed Neon database.
- Browser screenshot QA was blocked by failed Chromium downloads. Streamlit AppTest exercises widget behaviour but does not establish pixel layout, responsive appearance or browser accessibility.
- No container build was run in this environment because Docker is unavailable. The container definition must be built before container distribution.
- No real OIDC provider login, hosted data migration, new live Sarvam result or new GitHub docs publication was performed. The offline sample is not evidence of those integrations.
- No independent penetration test, compliance certification, data-retention implementation or hostile-tenant isolation is claimed.

## Safe cutover

The existing `autodocsync.streamlit.app` deployment is still the previous shared-password version. Keep this release in its review branch until the host has a trusted OIDC client, random cookie secret, exact HTTPS callback and explicit administrator identity. Configure these through the hosting secret manager, not a public issue or source commit. Back up the database, run `docsync-doctor --hosted`, apply migration 005, then complete the real sign-in/role and code-to-chat acceptance steps in SECURITY.md.

The public sample can be deployed separately without credentials. The connected workspace is an invite-only team beta, not anonymous public SaaS. Integrated repository maintainers/Actions workflows hold database credentials and must share the same trust boundary.
