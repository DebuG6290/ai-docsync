# CV evidence

Last audited: 2026-10-04. Evidence population and limitations must accompany numbers.

## 1. System capabilities

Python/Streamlit, PostgreSQL/pgvector, FastEmbed and Sarvam documentation workflow:
AST symbol detection, approved mappings/context, three-way impact decisions,
immutable proposal versions, authoritative human edits, targeted rejection revisions,
drift/race checked docs-only publication, verified indexing and cited versioned Chat.
These are implementation capabilities, not benchmark accuracy claims.
Baseline/incremental knowledge integrity gating and audits of existing approved
snapshots stage overlap evidence, block unresolved conflicts/uncertainty, and record
human resolutions before a new immutable version activates. See
[integrity contract](KNOWLEDGE_INTEGRITY.md); deployment validation is pending review.

## 2. Real repositories validated

- HTTPX: archived code-change evaluations and [human-merged documentation PR #7](https://github.com/DebuG6290/httpx/pull/7).
  Production Chat/activation totals need a scoped export before quantified reporting.
- OpenBull: [successful baseline index](https://github.com/DebuG6290/openbull/actions/runs/37153352939).
  The frozen helper-change case is permanently closed as an operational failure for
  this evaluation cycle. Original failure evidence is preserved in merged
  [PR #5](https://github.com/DebuG6290/ai-docsync/pull/5). Recovery experiments
  [PR #6](https://github.com/DebuG6290/ai-docsync/pull/6) and
  [PR #7](https://github.com/DebuG6290/ai-docsync/pull/7) are closed unmerged;
  the final recovery failed during summary aggregation before predictions/proposals
  persisted. No successful full OpenBull lifecycle is claimed.

## 3. Current benchmark metrics

The owner-confirmed `httpx-impact-human.v1` labels are frozen separately in commit
`7a1b9a23a1d71c4991c3eddcf3f6ff4ede4017c0`. S3 is excluded as ambiguous / not
adjudicated: an adjacent public capability does not automatically require a section
update. The original proposed packet and archived outputs remain unchanged.

Retrospective **development** scoring of archived `sarvam-105b` / `impact.v4`
predictions, dated 2026-10-02, on **3 controlled HTTPX source changes / 7 section
judgements**: TP=6, FP=0, FN=0, TN=1; precision **6/6**, recall **6/6**, F1
**12/12**, false-negative rate **0/6**, accuracy **7/7**, output coverage **7/7**.
This is a small correlated source-fixture population, not three live production
changes, hold-out performance, or quality of the currently deployed release.
See the [complete scoring report](../evals/httpx/measurement-review/SCORING.v1.md).

Seven synthetic cases are reported separately for diagnostics and excluded from
any CV headline metric. The two live HTTPX cases have frozen labels but remain
unscored because original per-section predictions are unavailable in the inspected
read-only archives. S1 and both live changes form one timeout-change capability
family. No new model calls, prompt tuning or model evaluation reruns were used.
The [HTTPX measurement inventory](../evals/httpx/measurement-review/INVENTORY.md)
separates live fork changes, controlled real-source changes, synthetic fixtures,
repeated executions and HITL replays. Archived rubric files remain historical
artifacts; only the separate owner-confirmed label version supplies ground truth
for this score. Retrospective archive review is development evidence, not hold-out
performance.
New deterministic metric primitives define precision, recall, F1, false negatives,
decision accuracy and retrieval recall; their tests are not an AI benchmark.

## 4. Reliability metrics

Regression-suite results belong to dated engineering validation, not production
reliability percentages. Production failure/retry denominators require an export.
Batch 0 local validation: **133 passed, 1 skipped** on 2026-10-04; the skipped test
requires ephemeral PostgreSQL/pgvector, covered separately by GitHub CI.
Batch 0 [CI run 37155513571](https://github.com/DebuG6290/ai-docsync/actions/runs/37155513571)
at `587b0b73feac915e22e20333daa8c5c195757394`: **134 passed**, including PostgreSQL/pgvector.
Batch 1 local validation: **162 passed, 2 skipped** on 2026-10-04; the skipped tests
exercise PostgreSQL/pgvector and concurrent scan deduplication/ownership in CI.
Batch 1 [CI run 37157275980](https://github.com/DebuG6290/ai-docsync/actions/runs/37157275980)
at `effccc06acd37ad0713e870f1968c57b5cf1673d`: **164 passed**, including both PostgreSQL checks.
These counts establish regression coverage, not model accuracy or field reliability.

## 5. Human-review metrics

Durable ACCEPT/MODIFY/REJECT events and version pointers exist. No production event
rates, independent factual support scores or reviewer-effort claims reported yet.

## 6. Latency and cost metrics

Provider latency and token diagnostics exist for recorded attempts; release timing
fields exist. No cost claim without observable usage and versioned pricing; no
end-to-end latency claim from provider-only timing.

## 7. Business-impact experiment metrics

Not measured. A controlled manual-vs-DocSync experiment is still required.

## 8. Candidate CV bullets

- Built a human-governed AI documentation and trusted-knowledge platform with
  immutable review history, drift-safe GitHub publication and repository-isolated cited retrieval.
- Evaluated on **N** independently labelled code-change cases, achieving **X%**
  impact recall, **Y%** supported proposal claims and **Z%** citation precision.
- Measured **T** median reviewer time reduction at **C** correctness across a
  controlled manual-vs-DocSync study. (Placeholder; do not publish as a result.)

## 9. Claims NOT YET defensible

Operational development evidence: the fixed public OpenBull baseline replay has
845 sections and 152,303 v1 versus 13,837 v2 candidate pairs (source commit and
method in `evals/openbull/narrowing-workload.json`). These are workload counts,
not labelled conflict outcomes. v2 conflict recall/precision and any latency/cost
improvement remain unmeasured; do not use this as a semantic-quality CV result.

Generalized AI accuracy; conflict-gate accuracy; production reliability percentage;
OpenBull full lifecycle; cost savings; hours saved; hold-out performance; comparative
prompt/retrieval gains; dependency-aware candidate benefits; large-scale or independent
capability-family coverage. Do not substitute synthetic tests or unverified archived
rubrics for real-repository headline claims.
