# Bounded impact analysis and recovery

## Root cause and fix

The failed HTTPX run [37126130969](https://github.com/DebuG6290/httpx/actions/runs/37126130969) exhausted Sarvam's 8,192-token impact output budget. The old call requested all mapped sections and its generic contract retry repeated that output scope.

Impact analysis now uses `IMPACT_MAX_SECTIONS_PER_CALL = 1`. `analyze(..., max_sections_per_call=...)` exposes the deterministic bound for controlled tests or future configuration. Sections are sorted by stable identity. Each call receives all original code changes, diffs, mappings and documentation: its target section is in `sections`; the other sections are in `related_documentation_sections`. A scope-only instruction says to assess target sections and read the others as context. The semantic impact prompt, strict schema and evidence fields remain unchanged.

Each batch must return its exact candidate set without missing, unknown or duplicate identities. The assembled set is validated again, and the existing UPDATE > UNCERTAIN > NO_CHANGE workflow aggregation is unchanged. Summaries are concatenated without another model call.

All batches finish before any section assessment or proposal is saved. Online persistence additionally refuses incomplete local results and publishes all review records in one database transaction. Failed batches leave the online case/job in ERROR, retain diagnostics and create no partial review. A successful retry reuses the case, clears its current error and retains earlier failure audits.

## Calls and diagnostics

For N candidates at the default bound, success normally uses N impact calls. Each non-length format/contract or retryable transport failure may receive the existing single retry: at most 2N calls for one attempt, stopping at the first failed batch. `finish_reason=length` gets **zero automatic retries** at the same scope/budget. No truncated content is accepted, even if it happens to parse. Output budgets remain mapping 4096, impact 8192 and revision 4096.

Batch plan/start/completion/failure events and existing Sarvam call diagnostics retain candidate counts, batch counts and IDs, batch number, attempt count, finish reason and available usage. Raw provider reasoning is not stored. An explicit whole-operation retry repeats earlier successful batches; partial batch results are diagnostics, not resumable approvals. This can incur additional Sarvam charges. Large individual sections can still truncate safely, and the full context is repeated per call, increasing input usage. No input token estimation or new infrastructure is introduced.

## Recover the existing HTTPX 8 to 9 change

1. Deploy the reviewed application release and copy the updated `integrations/httpx/docsync-analysis.yml` into `DebuG6290/httpx/.github/workflows/docsync-analysis.yml` on `master`. Both its reusable workflow reference and `application_ref` must use the same new release SHA. Keep the database and Sarvam secrets unchanged. The updated caller adds a manual recovery dispatch; changing pins alone does not change the old failed run's code.
2. Open HTTPX **Actions → DocSync code change → Run workflow** and select **master**.
3. Enter `before_sha = 17eea3e36ca8e90361843e6fc230b13e05d8682d` and `after_sha = 0bd67d36a676103794efafdd7f5ea6152f0b71d1`. The before value is the verified merge commit's first parent. The dispatch checks that both SHAs match an existing recorded analysis operation. If the original push covered additional commits, use the before SHA from that case's `git_context_prepared` or `action_received` History event instead; do not substitute HEAD.
4. Click **Run workflow** once. This explicitly enables retry. The new runner reuses the existing job/case, rechecks candidate documentation against the active approved index, then executes bounded analysis. Completed operations return without additional model calls; active operations retain the existing 30-minute lease protection. Unknown SHA pairs cannot create a new analysis through recovery dispatch.
5. Inspect the run, then refresh the DocSync review. Check the complete section set and batch diagnostics. Review and approve as usual. No new code-change commit is required.

Do not simply re-run failed run 37126130969: GitHub reuses the old run's workflow/application references. If context has drifted from the current approved index, recovery stops explicitly. Reconcile that drift before retrying. The live retry has not been executed by the implementation tests, and hosted database credentials were unavailable during this fix.

The index caller can keep its UI/lifecycle release pin because publication/index semantics did not change. Update it to the same new reviewed release if you want both integration callers aligned. Streamlit should continue deploying main; no schema migration is required for this fix.
