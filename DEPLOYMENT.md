# DocSync: free hosted deployment

The supported runtime is GitHub Actions → Neon PostgreSQL/pgvector → Streamlit Community Cloud. Sarvam is the only paid API. The Phase 1 reasoning prompts, schemas, mappings and targeted revision remain frozen.

## Cost Model

| Component | Intended demo cost |
| --- | --- |
| Public GitHub repositories / standard hosted Actions | ₹0 |
| Streamlit Community Cloud | ₹0 under free service limits |
| Neon PostgreSQL / pgvector | ₹0 within Neon Free limits |
| Local FastEmbed MiniLM | ₹0 API cost |
| Sarvam impact, targeted revision, chat | Usage-based API cost |

Free-tier terms and quotas may change; check provider limits before deployment. No required recurring infrastructure payment is the target. Do not provision larger Actions runners, paid Streamlit hosting, a Neon paid plan, or Render resources. Stop when a free quota is exhausted; no automatic upgrades or keep-alive polling.

Provider references: [GitHub billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [Streamlit deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [Neon Free storage announcement](https://neon.com/blog/neon-free-plan-1-gb-per-project). Neon announced 1 GB per Free project on October 2, 2026; use the console for the current storage, compute, network and branch quotas.

## 1. Publish this application release

Application: `DebuG6290/ai-docsync`, branch `main`. Monitored demo: `DebuG6290/httpx`, branch `master`. Publish the migration commit before installing the caller workflows. Note the full application commit SHA.

Copy `integrations/httpx/docsync-analysis.yml` and `docsync-index.yml` into the fork's `.github/workflows/`. The supplied callers pin BOTH the reusable workflow and application checkout to `6e5d6449c6d46cea9617c516329ab4f373be7ab1`. When updating releases, replace both references together with the same reviewed full SHA. The repository has only small integration files; application code stays in ai-docsync. Enable Actions on the fork. Allow reusable workflows and standard Ubuntu runners. Keep Actions permissions read-only. Do not enable secrets for untrusted PR workflows.

Reusable workflow inputs are plumbing: caller repository, monitored branch, and trusted event JSON. Push analysis reads the complete Git old/new diff, not the potentially truncated event commit list. Unsupported-symbol-only changes are recorded as skipped, never classified semantically as NO_CHANGE. A normal docs-only merge has no changed Python symbols and cannot recurse into Sarvam analysis.

## 2. Neon Free database

Create a Neon **Free** project with no paid upgrade. Copy its TLS connection string (`sslmode=require`). Use a direct connection for initialization if your pooler cannot run schema migrations; use a pooled connection for runtime.

Set `DATABASE_URL` locally without printing it, then run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m docsync.web.migrate
```

The versioned Alembic migration enables `CREATE EXTENSION IF NOT EXISTS vector`, creates the existing online tables, and adds/backfills explicit `human_modified` provenance. It preserves existing cases, approvals, audit records and vector chunks. Set `DOCSYNC_REPOSITORY=DebuG6290/httpx` and `DOCSYNC_MONITORED_BRANCH=master` to seed the approved mappings. Migration also runs in Actions before operations; credentials never appear in migration configuration.

Tables retain repositories, mappings, deliveries, finite jobs, cases, section assessments, model calls, proposals, immutable proposal versions, review actions, audit events, releases and hashes, knowledge versions, 384-dimensional chunks and chat turns. `jobs` is an operation ledger, not a continuously polled hosted queue. Temporary SQLite bridges live only during one operation; hosted durable data is PostgreSQL.

## 3. Fork Actions secrets

In HTTPX fork → Settings → Secrets and variables → Actions, add:

- `DATABASE_URL`
- `SARVAM_API_KEY`

`GITHUB_TOKEN` is built in and read-only. No App private key is needed in Actions. Indexing requires only `DATABASE_URL` and the built-in token. SARVAM_MODEL defaults to sarvam-105b.

The analysis workflow runs on push to master. The indexing workflow runs when a PR is closed and merged into master, or when baseline initialization is manually dispatched. The release must already exist in Neon with the exact PR number and immutable approved commit. PR names and filenames are not approval evidence.

Impact output is bounded to one target section per call while retaining full code and documentation context. Failed analysis can be explicitly recovered from the updated analysis caller's Run workflow inputs using the existing before/after SHA pair. See [analysis recovery](docs/ANALYSIS_RECOVERY.md) for call limits, diagnostics and the current HTTPX 8→9 recovery steps. Re-running an old pinned workflow does not load a newly published fix.

## 4. GitHub App for approved writes

Create an App with webhooks **disabled**, contents read/write, pull requests read/write and metadata read. Install it on **only DebuG6290/httpx**. Record App ID, installation ID and generate a private key. Do not give it Actions administration or organization permissions. Do not use a broad classic PAT.

The App is used only from Streamlit for publication. Actions reads use GITHUB_TOKEN. PRs are manually merged by the reviewer in GitHub.

Publication validates the exact accepted version IDs and original documentation hashes, applies the proven Phase 1 patcher, and creates only those documentation files in the Git tree. Immutable Git objects and the approved release snapshot are persisted before branch/PR creation. Retrying reuses the durable release and reconciles an already-created PR. Relevant context drift or a conflicting publication branch stops publication rather than overwriting it.

An unrelated branch advance can be published safely after ancestry, reviewed-code file overlap and reviewed-section hash checks. The new docs commit uses the validated current tip as parent; the branch is checked again before branch and PR writes. See [publication recovery](docs/PUBLICATION_RECOVERY.md) for safe retries, prepared-snapshot limits and the existing HTTPX case's exact UI steps.

## 5. Streamlit Community Cloud

Deploy `DebuG6290/ai-docsync`, branch `main`, entry point `streamlit_app.py`, Python **3.12**. `requirements.txt` installs the package and its dependencies. Copy `.streamlit/secrets.toml.example` into the Community Cloud secrets editor and replace placeholders. Never commit `.streamlit/secrets.toml`.

Required Streamlit secret names:

- `DATABASE_URL`
- `SARVAM_API_KEY`
- `GITHUB_APP_ID`
- `GITHUB_INSTALLATION_ID`
- `GITHUB_PRIVATE_KEY` (multiline PEM)
- `DOCSYNC_REVIEW_USERNAME`
- `DOCSYNC_REVIEW_PASSWORD` (long random password)

Configuration: `DOCSYNC_REPOSITORY`, `DOCSYNC_MONITORED_BRANCH`, `DOCSYNC_HOSTED=true`, optional `SARVAM_MODEL`. Keep GITHUB_TOKEN unset here. The application requires login before reads, mutations or model calls. Add Community Cloud viewer restrictions under sharing settings where available; provider restrictions are additional protection. The public repository contains no credentials.

Pages: **Home, Reviews, Knowledge, Chat, History, Settings**. Home prioritizes reviews needing attention. Reviews opens a focused section-by-section workspace with the recommendation, exact proposed diff, rationale and missing evidence. Code, assessment details and version history are expandable. Approval binds the displayed version. **Edit suggestion → Save edit → Approve update** creates an authoritative human version (`human_modified=true`) with separate explicit approval. Request revision saves the reason first and revises only the selected section. Uncertain sections require reasoned human triage. A NO_CHANGE section can receive a reasoned human override before the publication snapshot is created; the original assessment remains in history.

Streamlit applies additive schema migrations once per database/process after login. The release lifecycle migration adds merge confirmation, verification/index start, activation and status-check timestamps without replacing existing records. Knowledge shows the active approved snapshot separately from pending documentation releases. Chat retains older answers with their original citations/version and offers **Ask again using current documentation**. A merged PR is not labeled available to Chat until verified indexing activates it.

While operations are pending and the workspace is open, a 15-second fragment refreshes durable status. Known public documentation PRs are checked at most once per minute per active session. This is browser-session status refresh, with no permanent worker or keep-alive scheduler. Editor drafts survive navigation and automatic refresh within the session; they are durable only after Save edit. Use Refresh workspace for an immediate database refresh.

An approved case exposes **Create approved docs PR**. No polling worker is needed. The process records PENDING/PROCESSING/COMPLETED/ERROR operations. Failed/interrupted operations can be explicitly retried in the app; a 30-minute lease prevents a concurrent retry while a call may be running. Actions can be rerun after errors. Sarvam cannot be guaranteed exactly-once if the process stops after a billed response but before saving it. Completed durable results are reconciled before another call.

## 6. Initialize approved baseline

Before changing code, open the fork → Actions → DocSync index → Run workflow, select master and enter:

`b5addb64f0161ff6bfe94c124ef76f6a1fba5254`

This is the explicit human-approved demo baseline. Do not use the current branch tip implicitly: installing integration workflows already advances it. Baseline indexing is idempotent and cannot replace an initialized active index. Check the successful Actions run, Knowledge active version/source commit, and approved_baseline_indexed audit.

Ordinary analysis checks candidate documentation against active approved chunks. Unapproved doc drift causes an explicit context conflict before Sarvam sees that text; it must be reconciled by a human.

## 7. Exact D0 → D1 demonstration

1. Ask **What is the default timeout?** in Streamlit Chat. Record D0, expected five seconds, section/file citation, approved commit and knowledge version.
2. Change `DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)` to `Timeout(timeout=8.0)` in the HTTPX fork and merge to master. This symbol is a demo edit; no application semantic rule is based on its name.
3. Verify automatic DocSync code-change Actions run → live Sarvam → Neon case → Review Queue. Inspect all candidate sections, including advanced/timeouts and QuickStart.
4. Reject one proposal with a meaningful wording/evidence reason. Verify only its V2 is added. Inspect history. Accept the precise displayed versions; optionally save a human modification and explicitly accept it. Resolve any UNCERTAIN sections.
5. Create the approved docs PR from Streamlit. Inspect the docs-only diff; merge manually in GitHub.
6. Verify automatic DocSync index run. It verifies GitHub merged PR metadata, approved commit identity, merged file text and each section hash. Only changed approved sections get new embeddings; unchanged vectors/source provenance are copied. New version, active pointer, release/case state and activation audit commit atomically. Concurrent activation uses compare-and-swap protection.
7. Ask the same question. Record D1, expected eight seconds, citation to the newly merged approved documentation commit and new knowledge version. Pending, rejected and draft proposal text cannot enter retrieval.

Do not declare hosted acceptance until these artifacts exist. Local service tests cannot prove the hosted demo.

## Local development

SQLite supports service tests and exact Python cosine retrieval without paid services:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
# Configure ignored .env with local DATABASE_URL and review credentials.
.\.venv\Scripts\python.exe -m docsync.web.migrate
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
.\.venv\Scripts\python.exe -m pytest -q
```

For local PostgreSQL/pgvector, use `docker compose up --build` after setting .env variables; this starts Postgres and Streamlit on port 8501, with no worker. Existing FastAPI/Jinja routes and worker.main remain **legacy local compatibility** for existing tests; they are not the supported deployment path. render.yaml is removed.

## Resource and recovery limits

Community Cloud may sleep or restart; Neon may scale to zero. Embedding model initialization can be slow and memory intensive. One cached FastEmbed model is shared in Streamlit; the cache directory is temporary and holds no durable state. Standard Actions runners download embeddings during indexing. No keep-alive scheduler is introduced.

GitHub concurrency serializes repository analysis/index runs; the DB operation lease handles Streamlit retries. Streamlit revisions run synchronously. If deployment shows this is unreliable, the next change should dispatch a finite zero-cost Action, not provision a paid worker. Stale branches/context and altered merged text stop for review. There is no chat feedback/root-cause correction loop in this migration.
