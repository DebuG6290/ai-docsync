# Safe publication after unrelated branch advances

## Root cause

The publisher required the monitored tip to equal `case.after_sha` both before preparation and before branch creation. That blocked an approved review even when intervening commits changed only workflow configuration. The failed operation remains recoverable because its approved versions and review history are durable; the initial guard failed before creating a release or publication branch.

## Drift validation

The publisher reads current tip B, clones reviewed base A and B, and checks out B without executing repository code. It requires A to be B's ancestor. Every intervening commit, including merge diffs and reverted edits, contributes changed file identities. Any overlap with code paths from the stored changes/mappings blocks publication conservatively. This is mechanical file overlap, not a semantic impact rule.

Every reviewed candidate section must have a durable assessment. Current sections are located by stable section ID and compared with the durable `current_text`/`base_sha256` using the existing canonical LF hash helper. Missing/changed sections block publication. An unreviewed section elsewhere in the same Markdown file may change: its current content is retained.

If validation passes, the existing patcher applies only exact accepted version IDs on the B checkout. Human edits, human NO_CHANGE overrides, revisions and prior rejected versions retain their original history. The Git tree uses B's tree and changes only accepted Markdown files. The documentation commit's parent is B; the monitored branch is never rewritten. No model calls occur.

The backend records `publication_drift_validated` or `publication_drift_blocked` with reviewed base, validated tip, intervening commit/file counts, reviewed-code overlap, reviewed-section overlap and validation result. `publication_prepared` records the publication parent, and retries retain earlier audits.

## Race and prepared-snapshot safety

The monitored tip is checked again immediately before creating the publication branch and again before creating/reconciling the PR. A changed tip produces an explicit conflict. These are point-in-time checks; GitHub does not provide an atomic transaction spanning a base-branch check and PR creation. The documentation commit always retains its validated parent.

If a race stops preparation before any publication branch exists, explicit retry revalidates the new tip and rebuilds the prepared commit using the same release row and unchanged approved versions. Old immutable Git objects remain harmless. If a publication branch was already created and the monitored base subsequently advances, retry stops for reconciliation instead of rewriting that branch or risking a previously created PR. A prepared snapshot whose accepted version IDs differ is also blocked. No force pushes or resets are used.

## Retry the existing HTTPX case

Reviewed base: `0bd67d36a676103794efafdd7f5ea6152f0b71d1`.
Reported subsequent tip: `26dd676e93d775c8205c780672a3738fe9d0d4c6`.
A read-only GitHub comparison confirmed this pair is ahead by two commits with a net change to `.github/workflows/docsync-analysis.yml`. The actual publication retry still validates every intervening commit and current section against whatever tip exists at that time.

1. Deploy the fixed `DebuG6290/ai-docsync` main branch to Streamlit. If the app has not refreshed automatically, reboot it from Community Cloud's Manage app controls. No schema migration or new secrets are required.
2. Sign in and open **Reviews → the existing 8→9 review**. Refresh the workspace. Keep its existing accepted proposal versions.
3. In **Publish approved documentation**, expand **Included approved versions** to inspect the existing approvals.
4. Click **Resume publication** once. This explicitly retries the same `publish_docs` job. It increments the attempt, re-runs drift validation, and preserves the case and all review actions. A concurrent in-progress attempt remains protected by the existing 30-minute lease.
5. If successful, open the documentation PR. Verify the parent/current-base preservation, exact approved text and documentation-only diff before merging as usual. Approved-only indexing and Chat remain unchanged.

If current reviewed code/docs changed or history diverged, follow the explicit conflict message and obtain a fresh analysis/review. Do not repeatedly retry a real conflict. If the branch moves during preparation, Resume publication can revalidate provided no external publication branch was created; otherwise reconcile the existing branch/PR first.

HTTPX analysis/index workflow pins do **not** need updating for this fix: publication runs in Streamlit, and its updated code is loaded from application main. The existing batching release pins may stay unchanged. No new 9→10 code change is required for the reported workflow-only advance.

The live retry was deliberately not performed. Validation uses isolated real Git repositories and mocked GitHub transport; existing integration tests continue validating database, review and indexing contracts.
