# OpenBull first frozen-label analysis

Population: **one real independently human-labelled code-change case, two sections**.
This is a failed development evaluation, not a generalized AI accuracy estimate.

Labels were committed as `3a37f9ab33ac20e3a7943bf8d5d4467e61de6f72` before
analysis. The original preregistration was not changed. Its recorded SHA-256
identifies the original Windows working-tree bytes (CRLF); Git normalizes text
line endings, so use the original committed artifact and Git identity for portable
provenance rather than comparing that working-tree hash against LF checkout bytes.
Human decisions/rationales are separate from preregistered engineering claim
boundaries. No model result was used as a label.

- Application: `028113e1e223c2aa96bb6fe351e5ce5ef8264149`.
- Model/prompt: `sarvam-105b` / `impact.v4`; batch scope `sections.v1`.
- Before: `bce9dc7bff5ff9cd9053d8a273f948fa41e183b4`.
- After: `60bd5b7155bcbfc38495124d53ab88f866a8da1c`.
- Code: [OpenBull PR #3](https://github.com/DebuG6290/openbull/pull/3), merged.
- [Analysis run 37181176962](https://github.com/DebuG6290/openbull/actions/runs/37181176962), attempt 1, failed.
- Durable case: `c906609a-7706-4bc6-a0cd-046720596c98`.

## Original result

The first one-section batch (PRODUCT) failed with `finish_reason=length`.
No repair retry was scheduled; the SERVICES batch was never called.
The atomic analysis contract published no assessments or proposals. Failure is
retained as missing predictions, not excluded or converted to NO_CHANGE/UNCERTAIN.

| Section | Human label | Original observed prediction |
| --- | --- | --- |
| SERVICES trading-mode-service | UPDATE | MISSING: second batch unattempted |
| PRODUCT external-api | NO_CHANGE | MISSING: first batch truncated |

| Metric | Numerator / denominator | Value |
| --- | --- | --- |
| TP / FP / FN / TN | 0 / 0 / 1 / 0 counts | One operational missed impact |
| Precision | 0 / 0 | Unknown; no predicted positives |
| Recall | 0 / 1 labelled positives | 0% |
| F1 | 0 / 1 (2TP + FP + FN) | 0% |
| False-negative rate | 1 / 1 labelled positives | 100% |
| Exact decision accuracy | 0 / 2 labelled sections | 0% |
| Output coverage | 0 / 2 labelled sections | 0% |
| UNCERTAIN output rate | 0 / 2 labelled sections | 0%; no valid outputs, not confidence |

These operational scores include infrastructure/contract failure. There is no
valid semantic decision to score separately. Missing PRODUCT is not a true negative.
Proposal support/unsupported/insufficient-evidence rates and human outcome rates
are **unknown (zero adjudicable proposals/claims/review actions)**, never perfect.

## Observable operations

One provider attempt, zero retries; provider-reported input/output/total tokens:
13,426 / 8,192 / 21,618. Recorded attempt latency: 69,511.85 ms.
Workflow ran from 05:53:35 to last update 05:55:31 UTC on 2026-10-04;
this includes setup and is not end-to-end analysis latency. No review-ready proposal
exists. No pricing assumptions were applied, so cost remains unknown.

## Evidence and limitations

`observations.json` preserves the execution manifest and transcribed provider
diagnostic fields. `raw-audit-ui.txt` preserves their rendered, case-scoped source.
`metrics.json` was generated with the existing `docsync.evaluation.metrics.decision_scores`;
`metrics.csv` retains each numerator/denominator for aggregation.

The deployed provider client does **not** retain raw truncated response text;
only response shape, usage and failure diagnostics survived. Raw text cannot be
reconstructed and no extra call was made to obtain it. This is an evidence gap,
not a reason to fabricate output or hide the failed case.

No prompts were changed, no workflow was rerun, no proposal approved/published,
no semantic conflict scan invoked, and no knowledge version activated. OpenBull
continues using K1. Any separately authorized recovery must be a new versioned
evaluation and must not replace this first attempt or be called a hold-out result.
