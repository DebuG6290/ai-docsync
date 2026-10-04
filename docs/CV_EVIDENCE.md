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
  Human-labelled helper change [PR #3](https://github.com/DebuG6290/openbull/pull/3)
  merged as `60bd5b7155bcbfc38495124d53ab88f866a8da1c`. First analysis failed
  terminally on truncation; full code-change → review → docs merge → Chat remains outstanding.

## 3. Current benchmark metrics

One real independently human-labelled development case (two sections) now has a
preserved [first-attempt report](../evals/openbull/runs/2026-10-04-routing-fail-closed-attempt1/README.md).
Its single execution failed with `finish_reason=length`: no valid section outputs
or proposals. TP=0, FP=0, FN=1, TN=0; recall 0/1, F1 0/1, false-negative rate 1/1,
decision accuracy 0/2 and coverage 0/2; precision is unknown (0/0).
These include an operational contract failure, not independently scored semantic
decisions. No generalized quality claim or proposal-support percentage follows.
Archived reports remain evidence artifacts with original rubrics/provenance limitations.
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
Latest main [CI run 37161393354](https://github.com/DebuG6290/ai-docsync/actions/runs/37161393354)
at `028113e1e223c2aa96bb6fe351e5ce5ef8264149`: **167 passed**, including PostgreSQL checks.
OpenBull first frozen-label [analysis run 37181176962](https://github.com/DebuG6290/openbull/actions/runs/37181176962)
failed; it is retained in the evaluation denominator. No successful full OpenBull lifecycle claimed.

## 5. Human-review metrics

Durable ACCEPT/MODIFY/REJECT events and version pointers exist. No production event
rates, independent factual support scores or reviewer-effort claims reported yet.

## 6. Latency and cost metrics

Provider latency and token diagnostics exist for recorded attempts; release timing
fields exist. No cost claim without observable usage and versioned pricing; no
end-to-end latency claim from provider-only timing.
The failed OpenBull attempt recorded one `sarvam-105b` / `impact.v4` call, zero
retries, 69,511.85 ms attempt latency, and provider-reported 13,426 input + 8,192
output = 21,618 tokens. This is one failed attempt, not a latency distribution,
review turnaround, cost estimate or performance improvement. Raw truncated text
was not retained by the deployed client; diagnostics are preserved and the gap disclosed.

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
prompt/retrieval gains; dependency-aware candidate benefits; number of human-labelled
benchmark cases. Do not substitute synthetic tests or unverified archived rubrics.
