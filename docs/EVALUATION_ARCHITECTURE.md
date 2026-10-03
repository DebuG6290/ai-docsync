# Evaluation architecture

Audit date: 2026-10-04. Starting main: `b85b568259ab2c6316049883c4940df4185e7d11`.
This document defines measurement contracts, not model performance claims.

## Current architecture and trust boundaries

GitHub Actions reads fixed Git snapshots and Python AST changes, selects approved
code-to-section mappings, and runs section-bounded Sarvam impact assessments.
PostgreSQL stores cases, assessments, immutable proposal versions and human review
actions. Streamlit runs finite review/revision/publication operations over that same
store. Legacy FastAPI/worker entry points reuse the domain implementation.

Human acceptance pins an exact proposal version. Human edits create authoritative
versions. Rejection reasons drive targeted regeneration. Publication applies stored
approved text to a docs-only GitHub PR after ancestry, code overlap, section hash
and race checks. Human merge and exact merged-text verification precede indexing.
FastEmbed MiniLM produces 384-dimensional vectors; pgvector serves repository-scoped
retrieval. Index activation copies unchanged approved chunks and atomically switches
the active pointer. Chat stores its original knowledge version and citations.

Deployment: reusable analysis/index Actions plus Streamlit and Neon PostgreSQL;
no persistent queue is required. Additive Alembic migrations are under `migrations/`.
SQLite is a local test/preview backend, not the hosted deployment.

## Durable evidence inventory

| Entity | Measurements and provenance already available | Limitations |
| --- | --- | --- |
| Repository, CodeDocMapping | ownership, approved mappings and versions | no candidate-recall labels |
| GitHubDelivery | received_at, event, before/after commits | receipt is not code-change time |
| Job | kind, status, attempts, created_at, claimed_at | no normalized completion time; operations audit supplies boundaries |
| ChangeCase, SectionAssessment | created_at, commit pair, section decisions, evidence, uncertainty | model safe/unsupported claims are assertions, not labels |
| Proposal, ProposalVersion | immutable text/version, author, human_modified, created_at, accepted pointer | acceptance alone does not prove every claim |
| ReviewAction | ACCEPT/MODIFY/REJECT, reason, version, created_at | repeated actions are interactions; no reviewer active-time session |
| SarvamCall | operation, case, created_at, attempt metadata | case-less mapping/chat calls lack normalized repository ownership |
| AuditEvent | analysis/review/publication/index events, payload links | imported Phase 1 event time is online persistence time |
| DocumentationRelease, ReleaseSection | approved published text/hashes, merge/index/activation/status-check times | interrupted/older executions can have missing times |
| KnowledgeVersion, IndexedSection, ChatTurn | source commits, original version, citations, turn time | valid citation IDs do not prove semantic citation precision |

Sarvam attempt diagnostics currently include model, prompt version, candidate IDs,
retry count, finish reason, input/output/total tokens when supplied, contract errors,
error category and latency_ms. Truncation is terminal for unchanged scope; repair is
bounded. Missing token counts remain unknown. Missing pieces include call start/end,
normalized repository/run/release linkage, interrupted-attempt accounting,
versioned price assumptions, and reproducible evaluation-run metadata. No conflict
gate or conflict labels existed at the audit starting revision.

## Historical data and baseline access

HTTPX archived evaluations are under `evals/httpx/` and `evals/phase1_1/` with reports,
held-out manifests, fixture commits, adjudication and claim reviews. Reuse commit
fixtures and raw outputs; preserve reports verbatim. Legacy substring rubrics,
excluded infrastructure failures and revised scenario rubrics are not directly
comparable to the new metric contract. Archived claim-review authorship is not
verified by this audit; do not silently call it newly human-confirmed ground truth.

Public HTTPX evidence includes [approved documentation PR #7](https://github.com/DebuG6290/httpx/pull/7),
merged 2026-10-03, and [code change PR #5](https://github.com/DebuG6290/httpx/pull/5).
OpenBull [baseline index run 37153352939](https://github.com/DebuG6290/openbull/actions/runs/37153352939)
succeeded at commit `00673ebb95a8c08cd5523f6e5f7f6e196eaa47b9`.
Earlier failed analysis/index runs must remain part of reliability evidence.
An index success alone does not establish an OpenBull code-change lifecycle.

The current local configuration points to an empty SQLite database, not the hosted
store. No hosted totals are reported from it. Existing local HTTPX state databases
and preview databases are archives, not a substitute for a production export.
Production measurements require a repository-scoped read-only export or configured
database access; never copy credentials into evaluation artifacts.

## Metric contracts

Always report numerator, denominator, dataset/run and missing-data coverage. Values
are fractions. A zero denominator returns `null`/`no_samples`, never 0% or 100%.
Aggregation defaults to section-level micro scores unless explicitly macro.

| Metric | Numerator / denominator; label source |
| --- | --- |
| Impact precision | correctly predicted UPDATE / predicted UPDATE among independently labelled UPDATE/NO_CHANGE sections |
| Impact recall | correctly predicted UPDATE / all labelled UPDATE sections, including missing outputs and abstentions |
| Impact F1 | 2TP / (2TP + FP + FN) |
| False-negative rate | labelled UPDATE without UPDATE output / all labelled UPDATE; separately report strict NO_CHANGE misses |
| Decision accuracy | exact UPDATE/NO_CHANGE/UNCERTAIN matches / all independently labelled sections; missing outputs count incorrect |
| Output coverage / abstention | observed outputs / labelled sections; UNCERTAIN outputs / labelled sections |
| Candidate recall / precision | labelled impacted sections retrieved / all impacted sections; impacted candidates / labelled candidates; future hybrid changes require this baseline |
| Proposal factual support | supported atomic claims / human-adjudicated claims with sufficient evidence; separately report unjudged/insufficient claims |
| Unsupported-claim rate | unsupported atomic claims / human-adjudicated sufficient-evidence claims; never infer from the generating model's safe_claims |
| Review event rates | ACCEPT, MODIFY or REJECT events / all three event types, including repeat reviews |
| Unique-proposal outcomes | final outcome of each reviewed proposal / reviewed proposals; report unresolved proposals separately; distinct from event rates |
| Retrieval Recall@K | per-query relevant distinct section IDs in first K unique ranked section IDs / independently labelled relevant IDs; macro mean over queries with nonempty labels |
| Citation precision | human-supported cited claim/source relationships / adjudicated relationships |
| Answer support | human-supported answer claims / adjudicated answer claims |
| Conflict precision/recall | correct blocking-pair predictions / predicted blocking pairs; detected labelled blocking pairs / all labelled blocking pairs, including narrowing misses |
| Conflict classification accuracy | exact four-class prediction / adjudicated pairs; report pair-selection coverage separately |
| Terminal analysis job failure | currently ERROR jobs / COMPLETED + ERROR analysis jobs; a live snapshot, not historical attempt failure rate |
| Retried analysis jobs | attempted analysis jobs with attempts > 1 / all attempted analysis jobs |
| Calls/change | persisted provider attempts / analyzed changes, with diagnostic coverage; missing persistence can undercount |
| Latency | median and nearest-rank p95 of observed nonnegative durations; report samples and missing count |
| Intake to review-ready | case intake to first analysis_completed; not commit-to-ready or provider-only latency |
| Approval to activation | last approval_complete to release activated_at; missing timestamps excluded and counted |
| Estimated cost/change | recorded usage priced with identified versioned rates / analyzed changes; missing usage prevents a complete estimate |
| Estimated cost/accepted update | attributable analysis/revision usage cost / accepted documentation updates; define update as a distinct accepted section/version |
| Human effort reduction | (manual median active reviewer seconds - DocSync median active reviewer seconds) / manual median; only a controlled, correctness-adjudicated study |

Ground-truth UNCERTAIN is excluded from binary impact scores but included in
three-class accuracy. NO_CHANGE predictions of UNCERTAIN/missing are unresolved
negatives, not true negatives. Report confusion/coverage so abstention cannot inflate
accuracy. Predictions outside the labelled universe are listed without pseudo-labels.
Provider failures must stay in the evaluation manifest; report execution coverage
and treat missing impacted outputs as misses. Do not score only successful cases.

## Label representation and reproducibility

Each labelled case needs case_id, repository, before/after SHA, stable path::symbol
and path::heading IDs, full candidate universe, expected impacted/non-impacted
sections and decisions, safe/forbidden atomic claims, conflicts, notes and label
provenance. Human labels need reviewer identity, timestamp, evidence references,
adjudication status and immutable label version/hash. Synthetic fixtures explicitly
label their source as developer-authored; they are regression evidence, not field
accuracy. Review observations may suggest failures but cannot assign root cause.

Offline benchmark quality uses frozen labelled cases and predictions. Live-product
metrics use repository-scoped durable interactions, failures and timings. Keep these
populations separate. Do not turn acceptance, a valid schema or a successful Action
into impact accuracy, factual support or hours saved.

Freeze dataset content/hash, label version, split (development/regression/hold-out),
Git commit, model, prompt/retrieval/conflict versions, timestamps, decoding settings
and price version for every run. Preserve failures and raw observable diagnostics.
Store sanitized JSON/CSV and Markdown summaries as new run artifacts; do not
overwrite old runs. No iterative prompt tuning against the final hold-out set.

## Batch 0 implementation

`docsync.evaluation.metrics` implements deterministic ratios, impact/decision
scores, Recall@K, latency distributions and review event rates.
`docsync.evaluation.live.report(session, repo_id)` provides a read-only, scoped
baseline from current schema; quality and cost remain unknown without labels/rates.
Tests cover denominators, missing/uncertain predictions, chunk deduplication,
latency invalid observations and cross-repository isolation.
The audit also fixed equal-timestamp SQLite audit ordering: append order replaces
random UUID ordering as the tie-breaker, retaining existing rows unchanged.

Next: additive conflict staging/resolution gate; then pre-labelled OpenBull lifecycle,
benchmark harness, dashboard, feedback, comprehensive operation telemetry and study
instrumentation. Preserve existing approvals and active knowledge throughout.
