# Shared repository workspace

## Engineering assessment

The supported runtime remains reusable GitHub Actions, one PostgreSQL/pgvector database and one authenticated Streamlit application. Repository already owns cases, mappings, deliveries, jobs, releases, knowledge versions and chat turns; assessments and proposal versions belong through their case. Repository.active_index_version_id provides independent knowledge activation. No workspace, tenancy or account schema is needed, and no migration is added.

Previously Streamlit selected only DOCSYNC_REPOSITORY and displayed its deployment branch/name throughout every page. Mapping bootstrap unconditionally inserted HTTPX mappings. History included every baseline activation event, and retrieval did not verify that an active pointer belonged to its repository. Review detail rendered case.summary as the primary H1; cards used a truncated summary as their heading. These were presentation/bootstrap and boundary gaps rather than a need to duplicate the lifecycle.

The minimum change is an ID-based repository selector, settings derived from the selected durable row, explicit App-verified onboarding, scoped mapping confirmation and ownership checks at read/mutation boundaries. Existing approval, human edit, NO_CHANGE override, accepted_version_id, immutable release snapshots and publication drift validation retain their existing implementations. New baseline paths extend the same index handler rather than introducing another index implementation.

## Architecture and files

- `streamlit_app.py`: bootstrap/default selection, sidebar selector and connect entry point.
- `docsync/ui/workspace.py`: selected repository identity, operation settings and session boundaries.
- `docsync/online/onboarding.py`: input validation, GitHub App access verification, immutable discovery, reuse of mapping suggestions, audited human confirmation and pinned caller generation.
- `docsync/ui/onboarding.py`, `settings.py`, `home.py`, `knowledge.py`: progressive setup and clear connected/initialized states.
- `docsync/ui/components.py`, `reviews.py`, `style.css`: deterministic titles, bounded card previews, readable body prose and disclosed rationale.
- `docsync/ui/history.py`: scope activity before limiting results, including legacy baseline events linked through knowledge version IDs.
- `docsync/web/repository.py`: only DebuG6290/httpx receives the HTTPX bootstrap mappings; case-insensitive bootstrap lookup reuses its existing row.
- `docsync/web/github.py`: verify the installation's existing contents/pull_requests write grants during onboarding; no permission expansion.
- `docsync/web/indexing.py`: reject cross-repository active pointers and case/release activation.
- `docsync/online/operations.py`, `docsync/web/worker.py`: reject mismatched operation ownership before execution.
- `tests/test_multi_repository.py`: two-repository reads, mutation boundaries, mappings, access, baseline and Streamlit coverage. Existing HTTPX tests now identify the actual seed-eligible demo repository.

## Repository selection

The sidebar stores Repository.id in Streamlit session state; names are labels. A fresh session selects DOCSYNC_REPOSITORY if present, otherwise the first durable repository. Deployment configuration remains the initial bootstrap/default. Context settings use the selected row's full_name, monitored_branch and installation_id. Home, Reviews, Knowledge, Chat, History and Settings therefore operate on that row.

Switching repositories clears unsaved editor/review/chat/setup state while retaining login and page navigation. Saved versions, edits, reviews and chat history remain durable. Unsaved drafts survive navigation within the same repository, but are intentionally discarded when switching repositories. Save an edit before switching if it should be retained.

Review mutations verify ownership through Proposal/SectionAssessment → ChangeCase → Repository. The UI passes the selected repository ID into finite job execution. Job payload ownership is checked before claim or execution. Retrieval verifies active knowledge ownership. History filters by selected cases, jobs, repo_id and knowledge-version IDs, including older baseline audit records without repo_id.

## Connect the second real repository

1. Publish this reviewed application release and deploy/reboot the existing Streamlit app. Keep the same DATABASE_URL and review login. No additional Streamlit secret is required for a repository served by the configured GitHub App. DOCSYNC_REPOSITORY/DOCSYNC_MONITORED_BRANCH can remain HTTPX's defaults.
2. In GitHub, install or authorize the existing DocSync App on the second repository. Retain the existing contents read/write, pull requests read/write and metadata read permissions. Do not add a PAT or Actions administration permission. For another owner, install the same App on that owner's repository and record that installation's ID.
3. In Streamlit select **+ Connect repository**. Enter `owner/repo`, its monitored branch, and that App installation ID (visible in the installation settings URL).
4. Select **Verify GitHub App access**. DocSync exchanges an App token, checks the existing write grants, reads repository metadata and verifies the branch. Verification alone neither writes a repository row nor changes the remote repository.
5. Select **Connect verified repository**. A new Repository row and audit event are saved; the app selects it and opens Settings. Existing rows are reused without overwriting branch, installation or active knowledge.
6. In Settings → **Documentation**, select **Discover repository structure**. DocSync reads a fixed full commit SHA. Select relevant `.md` documentation and `.py` code files, then **Inspect selected files**. The parser reads Git objects without executing repository code. Unsupported Python syntax is reported. Inspect at most 10 code/15 documentation files at once.
7. In **Mappings**, select a small set of symbols and sections (maximum 30 of each per suggestion call). Select **Suggest relationships with Sarvam**, or use **Create a manual mapping** without a model call. Review each pair and reason; use **Confirm mapping**, choose another section, or **Ignore**. Only explicit confirmation creates an APPROVED mapping. Stable identities remain `path::symbol` and `path::heading`. Suggestions/ignored choices are session-local; confirmations and their source commit/reason are durable and audited.
8. In **Integration**, download/copy both caller files into exactly `.github/workflows/docsync-analysis.yml` and `.github/workflows/docsync-index.yml` in the second repository. They contain its monitored branch and the running application's full Git release SHA in BOTH the reusable workflow and application_ref pins. They contain no HTTPX baseline default. Use a reviewed setup commit/PR and merge it yourself. The app does not create setup branches or push files.
9. Add Actions secrets `DATABASE_URL` pointing at the SAME workspace database and `SARVAM_API_KEY` for analysis. Indexing needs only DATABASE_URL. Enable Actions/reusable workflows and standard runners. Actions uses its built-in read-only GITHUB_TOKEN; keep App private keys in Streamlit. No paid service is introduced.
10. Review and explicitly approve the documentation source commit. In that repository's **Actions → DocSync index → Run workflow**, choose the monitored branch and enter the full 40-character source commit in `baseline_sha`. This dispatch is the human approval of the baseline; discovering/connecting/mapping does not approve knowledge.
11. Wait for a successful indexing Action. Refresh Streamlit and verify **Knowledge** shows an active version with the chosen source commit. Only then use Chat or start code-change analysis. Initialization cannot replace an existing active version; failures do not activate partial knowledge.
12. Make a supported mapped Python change in the second repository. Verify its normal analysis → review/edit/revise/approve → docs PR → human merge → verified indexing → Chat lifecycle. Switch back to HTTPX and verify its reviews, active knowledge and chat history remain separate.

The second repository name is chosen by the operator; this release does not perform live setup on another repository.

## Baseline semantics and compatibility

The existing baseline handler remains explicit, idempotent and approved-only. It reads Markdown under `docs/`, preserving HTTPX's original coverage, plus documentation paths referenced by approved mappings (including README.md or another documentation directory). Files are read at the selected Git commit, never from a modified worktree. Missing mapped documentation or empty baseline stops initialization. Existing atomic KnowledgeVersion activation and concurrent activation protection remain in place.

Connection adds no trusted content and does not assign active_index_version_id. Chat cannot retrieve an uninitialized repository. Existing HTTPX records, mappings, approvals, versions, publication history and active knowledge are preserved; no reconnect or reinitialization is required.

Existing HTTPX callers can still serve HTTPX on their old release. Update both their reusable-workflow and application checkout pins together to this reviewed implementation SHA for consistent new ownership checks and lifecycle behavior. A second repository MUST use this release or newer: old application releases seed HTTPX mappings into arbitrary repositories. The Integration step generates matching pins from the running checkout. Install only a committed/reviewed application release.

## Review readability

Before: raw model summary could become several lines of enormous H1 text, including section IDs and evidence chains. Home/review card headings also used model prose.

After: review H1 comes from deterministic assessment count or source commit (`3 documentation sections to review`, `Review code change 0bd67d3`), with repository/commit metadata underneath and existing status badges. **Assessment summary** shows escaped, bounded body prose; longer text remains readable behind **Full assessment summary**, limited to approximately 80 characters per line by `max-width: 80ch`. Standalone decision tokens are omitted from narrative surfaces; status badges carry decisions. Cards have deterministic titles and escaped previews bounded to 180 characters and two visible lines. Section rationale is disclosed once, with technical evidence/version history in separate expanders. Model Markdown cannot create headings or navigation. Existing wrapping diff/mobile comparison styles remain, with prose wrapping for long identifiers.

## Manual steps and remaining limits

App installation ID entry, workflow installation/merge, Actions secrets and explicit baseline dispatch remain manual. Settings can validate live App access on demand; workflow installation status is operator-confirmed, not inferred from merely downloading callers. Access is checked again by real GitHub operations; a recorded installation is not a promise that access cannot later be revoked. Supported analysis remains Python and Markdown. No enterprise multi-tenancy, RBAC, new worker, duplicate database, automatic approvals or new paid infrastructure is included.

Local tests use synthetic repositories and mock external services. Full hosted acceptance still requires the operator's second repository and successful real Actions/publication/indexing artifacts.
