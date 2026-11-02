# DocSync

**Keep documentation aligned with code, with a human deciding what becomes trusted knowledge.**

DocSync watches a Python repository, suggests targeted Markdown updates, and gives reviewers the code evidence and exact text to approve. It creates a docs-only pull request. After a verified merge, approved documentation becomes available to cited chat.

**v0.3 is an invite-only, self-hosted team beta.** Run one workspace per trusted team. Other people can try the offline sample or deploy their own workspace. This is not a public multi-tenant SaaS or a compliance-certified system.

## Try it in a few minutes

Requirements: Python 3.12 and Git. Python 3.12 is the tested release runtime.

```bash
git clone https://github.com/DebuG6290/ai-docsync.git
cd ai-docsync
python -m venv .venv
# macOS / Linux / Git Bash
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
docsync-demo
```

Open the local URL printed by Streamlit. Inspect the 5 → 8 second code change, edit the sample suggestion, approve its exact version, simulate a merge, and watch the approved source change. Download the approved Markdown or reset the sample.

The sample needs **no API key, account, database server, repository access or model download**. Each browser session gets an isolated in-memory workspace. It uses real approval, immutable version and index activation services. Suggestions and GitHub merges are scripted, and the answer panel retrieves the approved source directly. It does not demonstrate live model quality or a real GitHub merge. Closing the session discards its sample data.

## Use it with your own repository

The connected workspace needs PostgreSQL/pgvector, a Sarvam key, an OIDC identity provider and a GitHub App. The existing GitHub Actions → PostgreSQL → Streamlit deployment remains supported; no persistent paid worker is required.

1. Copy `.streamlit/secrets.toml.example` into an ignored `.streamlit/secrets.toml`, or paste it into your hosting secret manager. Configure PostgreSQL with TLS, model credentials and GitHub App credentials.
2. Register an OIDC application with your provider. Its exact redirect URL is `https://YOUR_APP/oauth2callback`. Set the five `[auth]` settings, including a cryptographically random cookie secret of at least 32 characters.
3. Set `DOCSYNC_AUTH_MODE="oidc"` and `DOCSYNC_HOSTED="true"`. Grant access through `DOCSYNC_ACCESS_POLICY`. Members are matched by the **exact provider issuer + subject**, not their email or domain. If you do not know your subject, sign in once: the no-access screen shows your own issuer/subject for the administrator to add. Keep an explicit administrator in the policy.
4. Run `docsync-doctor --hosted`. It checks configuration without network calls or printing secrets. Run `docsync-migrate` against a backed-up database, then deploy `streamlit_app.py` to the configured HTTPS origin.
5. Sign in as an administrator and choose **Connect repository**. Install the GitHub App only on intended repositories. Reviewers can discover Python/Markdown files, confirm mappings, download caller workflows pinned to this release, and explicitly initialize a reviewed baseline.
6. Change code on the monitored branch. Review suggestions, approve exact versions, create the documentation PR, and merge it in GitHub. Knowledge activates only after the merged text and approved snapshot are verified.

For provider setup, workflow installation and recovery, see [DEPLOYMENT.md](DEPLOYMENT.md). For the threat model, data handling and release gates, read [SECURITY.md](SECURITY.md).

### Access policy

```json
{
  "version": 1,
  "members": [
    {"issuer": "https://accounts.google.com", "subject": "YOUR_SUB", "admin": true},
    {"issuer": "https://accounts.google.com", "subject": "REVIEWER_SUB", "repositories": {"your-team/project": "reviewer"}},
    {"issuer": "https://accounts.google.com", "subject": "READER_SUB", "repositories": {"your-team/project": "reader"}}
  ]
}
```

| Role | Access |
| --- | --- |
| Reader | Assigned repositories, reviews/history/approved knowledge, bounded questions |
| Reviewer | Reader access plus mapping setup, human edits/approval, conflict decisions and approved publication |
| Administrator | All workspace repositories and repository connection management |

An OIDC login alone grants nothing. Newly connected repositories require explicit grants for ordinary members. Policy changes take effect when the app reloads its deployment configuration; browser sessions are rechecked on their next rerun. Identity-token expiry and a maximum eight-hour token age are enforced. Sign out when finished, especially on shared devices.

## Costs and data handling

Selected code, documentation and revision instructions go to **Sarvam** for analysis. Chat sends the question and selected approved passages. FastEmbed computes embeddings locally, downloading the model on first real use. Your database stores review evidence, proposals, approved text, model diagnostics, audit events and repository-shared chat history. Do not onboard material you are not authorized to send to the configured provider.

Default UI allowances: 30 chat operations and 20 model-action operations per member/repository/UTC day; 200 model operations per repository/day shared by members; five operations per member/repository/minute. Counters persist across sessions and failed external operations consume their reservation. These limit **operations, not money or tokens**; one revision or conflict scan can contain several provider requests. Trusted Actions runs have separate concurrency/timeouts. Set provider billing limits as well.

## Development

```bash
python -m pip install -c requirements.lock -e '.[test]'
python -m pytest -q
```

For local development of the real workspace, set `DOCSYNC_AUTH_MODE=local`, `DOCSYNC_HOSTED=false`, a local database URL and a reviewer password of at least 12 characters. Bind it to loopback:

```bash
streamlit run streamlit_app.py --server.address=127.0.0.1
```

Local password mode is unavailable in hosted mode. The legacy FastAPI surface is local compatibility only and rejects workspace/webhook access in OIDC or hosted mode. Use `demo_app.py` for a public sample deployment with **no production secrets**. Keep its database and secret set separate from your real workspace.

Dependencies are pinned to exact versions in `requirements.lock`; `requirements.txt` applies it as constraints. Regenerate deliberately with `uv pip compile pyproject.toml --extra test --extra security --output-file requirements.lock`, audit, test, then review the lock diff. CI also audits dependencies and runs medium/high severity static security checks.

## Limits and release status

- Python symbols and Markdown sections are supported. Explicit mappings determine assessment coverage; unmapped code is a coverage gap.
- Model suggestions can be wrong, incomplete or truncated. A citation establishes source provenance, not factual correctness. Human review remains required.
- There is no automatic deployment, merge, anonymous repository onboarding or automatic approval.
- A team workspace trusts its deployment operators, database administrators and integrated Actions maintainers. Those workflows hold database credentials. Use separate instances/databases for mutually untrusted teams or repositories.
- This release has application-level access controls and regression tests, but no independent penetration test. See the release evidence for completed checks and outstanding hosted acceptance.

MIT licensed. See [LICENSE](LICENSE).
