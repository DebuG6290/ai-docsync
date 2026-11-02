# Security policy and deployment boundary

## Supported release

v0.3 is a self-hosted team beta with a separate credential-free sample. The supported shared workspace uses Streamlit with OIDC, explicit access policy, TLS and trusted Actions workflows. The default authentication mode is OIDC; missing configuration fails closed.

This is one organizational trust boundary, not a hostile-tenant hosting platform. Integrated repository maintainers can edit Actions workflows that hold database credentials and must be trusted as workspace operators. Per-user repository ACLs protect the application UI, not a compromised database/CI/operator. Use separate workspaces/databases for mutually untrusted repositories or teams.

## Controls

| Threat | Control | Remaining limit |
| --- | --- | --- |
| Unauthorized login / open signup | Native OIDC; exact issuer + subject invitations; default deny | Operator must configure a trusted provider and protect client/cookie secrets |
| Reader privilege escalation | Server-side roles before reads/mutations/jobs; explicit repository queries | Administrators see every repository in their workspace |
| Cross-repository IDs | Context verifies repository ID/name; existing proposal/job/index ownership checks | No database row-level tenant security for untrusted CI clients |
| Long-lived identity cookie | Required `iss`, `sub`, `iat`, `exp`; token expiry and maximum eight-hour age | Logout does not terminate other open Streamlit sessions; policy changes must reload deployment config |
| Repeated model calls | Atomic database allowances, shared repository/day cap, per-minute burst bound, input limits | Operation counts are not a financial cap; Actions/provider limits are separate |
| Unreviewed knowledge / prompt injection | Approved-only retrieval; parse code without executing it; explicit approval; immutable versions; merged text/hash verification | Prompts cannot guarantee factual correctness or neutralize all malicious reference content |
| Git command abuse / secret leakage | Validate owner/repo and full SHAs; argv subprocesses; disable file/ext protocols, hooks and diff text conversion; timeouts; sanitized remote errors | Very large repositories can consume resources; only trusted maintainers may onboard them |
| Browser content injection | Escape custom HTML; ordinary repository text uses safe Markdown defaults | Upstream Streamlit/identity-provider security remains trusted |
| Secret exposure | Ignore secret files; no credentials in Git URLs; preflight prints status/names only; non-root container | Operators must rotate exposed keys and restrict backups/logs |

The public sample uses scripted fixtures, isolated in-memory state and direct source retrieval. It never reads production configuration, calls a provider, downloads an embedding model or publishes to GitHub. Run it separately with no production secrets. Simulated merges are labelled; sample results are not live acceptance evidence.

## Data flow and retention

- **Sarvam:** selected code/documentation, revision instructions, chat question and retrieved passages. Deployment owners must review provider retention/usage terms before using private material. No zero-retention or regulatory compliance claim is made.
- **Database:** repository configuration, source snippets, generated/human proposals, review decisions, merge/index provenance, diagnostics and shared repository chat. UI audit events carry a pseudonymous actor identifier derived from issuer/subject.
- **Disk:** temporary Git clones are removed on context exit; embedding weights are cached locally. The sample has no persistent database.
- **Retention:** evidence and chat have no automatic deletion in this milestone. Usage counters older than the current UTC day are discarded. Define retention, backup and deletion procedures before using sensitive data. Arbitrary cascade deletion is not provided.

Do not give users raw database connections or broad GitHub tokens. The GitHub App needs metadata read, contents read/write and pull requests read/write, installed only on selected repositories. Disable App webhooks for the supported Actions deployment. Keep App write credentials only in the workspace; Actions uses its built-in read-only token for GitHub reads.

## Before an internet-facing team deployment

1. Review exact OIDC issuer/subjects and role policy. Use provider MFA/session policy where available. Set a random cookie secret, exact HTTPS redirect URI and `DOCSYNC_HOSTED=true`.
2. Run `docsync-doctor --hosted`. Test actual sign-in, uninvited-user denial, reader/reviewer separation and expiry on the deployed origin.
3. Back up the database and test additive migration/restore. Use PostgreSQL over TLS and restrict database/backup access.
4. Pin callers and application checkout to the same reviewed full SHA. Review integrated repository maintainers and Actions secret access. Never expose secrets to untrusted PR workflows.
5. Complete real code change → review → docs PR → manual merge → verified activation → cited chat. Check that drafts stay out of retrieval and another repository cannot read the result.
6. Configure provider billing limits, observe usage, audit dependencies and rotate secrets after exposure. Keep the public sample separate.

These are deployment acceptance requirements, not a claim of a completed hosted release or independent penetration test.

## Reporting a vulnerability

Do not post credentials or private source in public issues. Use GitHub private vulnerability reporting if enabled. Otherwise contact the repository owner privately before publishing a sensitive reproduction. Include the version, impact and a minimal redacted reproduction. No response-time guarantee is currently offered.

## Primary references

- [Streamlit authentication](https://docs.streamlit.io/develop/concepts/connections/authentication)
- [Streamlit login configuration](https://docs.streamlit.io/develop/api-reference/user/st.login)
- [OpenID Connect ID-token claims](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)
- [GitHub Actions secure use](https://docs.github.com/en/actions/security-and-hardening/security-guides/security-hardening-for-github-actions)
