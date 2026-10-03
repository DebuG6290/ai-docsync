# DocSync Phase 2 deployment and demo

## Stack

- FastAPI backend and server-rendered Jinja pages.
- Render web service plus a small background worker and managed PostgreSQL.
- PostgreSQL `pgvector` stores dense vectors for local `sentence-transformers/all-MiniLM-L6-v2` embeddings (FastEmbed, 384 dimensions).
- GitHub App handles signed push and pull-request webhooks and uses installation-scoped tokens to fetch code and create docs-only branches/PRs.
- Phase 1's `analyze`, `revise_rejected`, and hash-checked `apply_case` functions remain the impact/revision/patch path.

The included Render blueprint uses non-free persistent service/database plans. Render's free Postgres expires after 30 days, and free web-service filesystems are ephemeral, so those plans are unsuitable for the durable case/audit/index state. Review the current [Render pricing](https://render.com/pricing) before creating resources.

## Deploy the DocSync application

The current workspace has no Git remote or connected Render account. To make it available to Render, push this project to an application repository that you control. The HTTPX fork is a separate repository configured below. Do not copy the ignored `.env`, `.docsync-state`, `.httpx-testbed`, `.httpx-scenarios`, or the unrelated `test` path into the application repository.

1. Create an application repository and push the DocSync source, including `render.yaml`.
2. In Render, choose **New → Blueprint**, connect that application repository, and apply `render.yaml`. This creates the web service, worker, and PostgreSQL database.
3. In the web and worker services, set the `sync: false` values listed below. Use the same values for both services. Store secrets only in Render's environment-variable UI.
4. Set `DOCSYNC_BASE_URL` to the web service's HTTPS URL. The webhook endpoint will be `https://<service>.onrender.com/webhooks/github`.
5. Confirm `/health` returns `{"status":"ok"}`. The UI uses HTTP Basic authentication with the configured review username and password.

## Environment variables

Required on both the web and worker services:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Render's internal PostgreSQL connection string; supplied by the blueprint. |
| `SARVAM_API_KEY` | Sarvam API key. Never put it in GitHub or audit fields. |
| `SARVAM_MODEL` | `sarvam-105b` unless the account uses a different supported model. |
| `GITHUB_APP_ID` | Numeric App ID from GitHub App settings. |
| `GITHUB_INSTALLATION_ID` | Installation ID for the one HTTPX fork installation. |
| `GITHUB_PRIVATE_KEY` | Contents of the App's PEM private-key file, pasted into the host secret field. |
| `GITHUB_WEBHOOK_SECRET` | A new high-entropy secret entered both in the GitHub App and host secret field. |
| `DOCSYNC_REPOSITORY` | Exact allowlisted fork name, such as `OWNER/httpx`. |
| `DOCSYNC_MONITORED_BRANCH` | `master` for the current HTTPX baseline, or the fork's actual branch name. |
| `DOCSYNC_REVIEW_USERNAME` | Reviewer login name. |
| `DOCSYNC_REVIEW_PASSWORD` | A unique long password for the review surface. |
| `DOCSYNC_BASE_URL` | Public HTTPS base URL of the Render web service. |

`DOCSYNC_EMBEDDING_MODEL` defaults to `sentence-transformers/all-MiniLM-L6-v2`. Its ONNX weights download the first time the service indexes or searches documentation. No provider receives embedding requests.

## Register and install the GitHub App

Create the App under your GitHub account or organization, then configure:

1. **Webhook URL:** `https://<service>.onrender.com/webhooks/github`.
2. **Webhook secret:** set a fresh random value and copy that same value to `GITHUB_WEBHOOK_SECRET` in Render.
3. **Repository permissions:** Contents **Read and write**; Pull requests **Read and write**. Metadata read access is GitHub's default. The app uses contents access to fetch code and push the approved docs branch, and pull-request access to open the review PR.
4. **Events:** `push` and `pull_request` only. The worker processes pushes to the configured monitored branch and indexes only merged DocSync PRs.
5. Generate an App private key. Enter its PEM text in Render's `GITHUB_PRIVATE_KEY` secret field. Do not commit or paste it into chat.
6. Install the App on **only the HTTPX fork**. Use the installation ID from the installation settings URL for `GITHUB_INSTALLATION_ID`.
7. Set `DOCSYNC_REPOSITORY` to the exact `owner/repository` name of that fork. The server rejects all other repositories.

GitHub's webhook HMAC validation uses `X-Hub-Signature-256` and a constant-time comparison. The App is installation-scoped, and no repository code is run; the worker only fetches Git objects and parses Python/Markdown.

## Run locally

1. Install Docker Desktop and Docker Compose.
2. Add the variables above to the ignored local `.env` file (the existing file may already contain the Sarvam key; preserve it). Compose supplies `DATABASE_URL` internally; do not replace it with a Render URL locally.
3. Run `docker compose up --build` from this directory.
4. Visit `http://localhost:8000`. A local public webhook requires a tunnel whose URL is configured in the GitHub App; never expose a development server without the webhook secret and reviewer password.

## D0 → code change → review → D1

1. Sign in and select **Index approved baseline** once. The worker indexes Markdown sections under `docs/` at the configured monitored branch SHA. This is the accepted baseline for the demo.
2. Open **Chat**, ask exactly `What is the default timeout?`, and record the answer plus its file, heading, approved commit, and index-version citations. This is D0.
3. In the HTTPX fork, change the default timeout value from 5 to 8 seconds and push/merge that code-only change into the configured monitored branch. No DocSync CLI operation starts the flow.
4. Open the DocSync review queue. Follow the GitHub delivery and case. Inspect changed code, diff, mapped sections, current text, Sarvam rationale, evidence completeness, missing information, safe claims, and unsupported claims.
5. Reject one proposal with a concrete reason. Wait for the worker to add the targeted Sarvam revision as a new version, confirm only that proposal changed, then either accept that version or edit it and explicitly accept the human version. Accept every other UPDATE proposal. Resolve any UNCERTAIN sections in the triage panel.
6. Wait for the case to link a docs-only branch and PR. Review/merge that PR in GitHub; DocSync does not auto-merge.
7. The `pull_request` merged event verifies that the approved section text is present at the merged SHA, embeds just those sections, copies unchanged active sections forward, and atomically switches the active index pointer. Pending/rejected/revision proposals are never selected for indexing.
8. In **Chat**, ask exactly `What is the default timeout?` again. This is D1. Verify that the cited section is from the merged approved documentation commit.
9. Open the case's **Audit timeline** to inspect delivery, analysis, proposal/revision, review, PR, and index events.

## Local test commands

Install the project and test extra into the active virtual environment, then run:

```powershell
& .\.venv\Scripts\python.exe -m pip install -e ".[test]"
& .\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp
```

Infrastructure tests use SQLite and fake GitHub/model boundaries; the deployed case-analysis, revision, and chat paths use real Sarvam calls. The tests do not substitute for installing the App, deploying the services, and completing the D0/D1 GitHub demonstration.
