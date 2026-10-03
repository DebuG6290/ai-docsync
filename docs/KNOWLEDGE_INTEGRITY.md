# Knowledge integrity gate

## Purpose and workflow

Two approved sections can describe the same capability incompatibly. The gate
stages a new candidate snapshot before activation. Human baseline approval and
exact verified merged release text remain the prerequisites; semantic compatibility
does not approve new text. Existing approved knowledge stays active during review.

Baseline: explicit approved SHA → all candidate sections → plausible pairs → semantic
assessment / human resolution → reverify baseline → activate.

Incremental: exact verified release sections + current approved snapshot → pairs
involving changed sections → assessment / resolution → reverify release → activate.
Unchanged chunks retain vectors and source commits. Changed sections replace their
old versions rather than being compared against the same obsolete section.

Existing knowledge: Knowledge → **Audit current approved knowledge for conflicts**
→ scan/resolution → **Activate reviewed integrity snapshot**. This can only copy the
existing approved snapshot and apply explicit human exclusions. It cannot add new
documentation. Old versions and historical Chat provenance are retained.

## Candidate narrowing and semantic classes

`lexical-overlap.v1` selected shared meaningful heading terms or at least two shared
non-stopword content/heading terms. It is generic, deterministic and uncapped;
selection evidence is retained. No filenames, repositories or specific capabilities
drive selection. It can miss paraphrases with no lexical overlap; candidate recall
requires independently labelled all-pair cases before claiming detection accuracy.
Embedding narrowing is a future measured option, not an unmeasured improvement.

`distinctive-overlap.v2` replaces the large-corpus rule: shared heading terms must
occur in at most 10% of headings; body terms must occur in at most 5% of sections
(both have a two-section floor), with at least two shared distinctive terms and
binary IDF cosine similarity at least 0.25. Corpora of 20 or fewer sections retain
the original overlap behavior. These are candidate signals, never semantic verdicts.
There is no top-K cap. Versioned fingerprints stage new evidence without rewriting
old scans. This policy can miss overlaps and requires labelled recall evaluation.

Live OpenBull auditing exposed 152,303 candidates across 845 sections. A fixed-commit
public-source replay produced 13,837 v2 candidates; see
`evals/openbull/narrowing-workload.json`. This measures workload only. It does not
establish semantic accuracy or end-to-end latency/cost. Do not automatically scan
an entire large candidate corpus merely to produce demo numbers.

Integrity review selects one durable scan and uses SQL counts plus pages of ten
assessed unresolved pairs. Unassessed pairs remain blocking but do not get premature
resolution forms. All evidence and historical scans remain accessible; pagination
does not change activation eligibility or discard off-screen conflicts.

`conflict.v1` assesses one exact pair with full section content, context and source
commit metadata. Metadata and lifecycle signals cannot establish authoritative truth.
Claim excerpts must appear verbatim in their sources. The four classes are:

| Class | Meaning | Activation behavior |
| --- | --- | --- |
| NO_CONFLICT | Compatible claims | Gate can proceed under existing approvals |
| SCOPE_DIFFERENCE | Explicitly supported different scopes/entities/configurations | Gate can proceed under existing approvals |
| VERSION_DRIFT | Incompatible lifecycle/version claims, possibly different stages | Human resolution required |
| HARD_CONFLICT | Incompatible claims about the same entity/scope | Human resolution required |

An independent `uncertain` flag and missing-information list block activation even
when classification is NO_CONFLICT. Unassessed pairs also block activation.
Provider/contract failure remains ERROR, never semantic NO_CONFLICT.

Each invocation assesses at most four new pairs and checkpoints each result. Larger
scans return PENDING and resume without repeating completed pairs. No pair is dropped
to satisfy the batch limit. Sarvam's existing bounded repair/length handling applies.

## Human review

Knowledge and Settings → Baseline show source A/B, exact content, provenance, model
reason, uncertainty and all assessed pairs. A rationale and authenticated reviewer
identity accompany every durable resolution:

- Prefer A/B excludes the other whole section from trusted retrieval.
- Different scopes keeps both after an explicit human scope judgement.
- Exclude A, B or both removes those sections from the next trusted snapshot.

Preference does not edit GitHub documentation or manufacture a reconciled claim.
Exclusions can resolve other pairs involving the same section. An empty trusted
snapshot cannot activate. Resolutions are insert-only; exact repeated submission is
idempotent, a conflicting repeated submission is rejected. Root-cause/quality labels
are not silently inferred from exclusion or preference actions.

## Durable records and state transitions

Additive migration `004_conflicts` adds KnowledgeScan, KnowledgeConflict and
ConflictResolution. Pair/resolution ownership uses composite repository foreign
keys. Snapshots bind repository, parent knowledge version, source commit, all content
and provenance, changed IDs, mode and narrowing/prompt versions through SHA-256.
Replay finds the same scan; changed evidence creates a new scan. Accepted proposal,
review and Chat history are never rewritten.

States: PENDING → SCANNING → PENDING (more pairs), REVIEW_REQUIRED or READY;
SCANNING → ERROR on failure; explicit scan retry resumes unassessed pairs;
human resolution → READY when every relevant blocking/uncertain/unassessed pair is
resolved; READY → ACTIVATED atomically with the new knowledge version.

A 30-minute scan lease prevents concurrent model work. Repository/scan locks,
content hash validation and existing active-pointer compare-and-swap prevent stale
or cross-repository activation. A scan against an old parent cannot authorize a new
snapshot. Model attempt diagnostics persist independently of assessment success.

Actions/legacy worker operations reaching this boundary become WAITING_REVIEW;
releases become KNOWLEDGE_REVIEW. This is an expected workflow boundary, not a
successful activation or provider failure. Resolve in Streamlit and resume the
original finite operation, which verifies GitHub evidence again before indexing.
Chat continues using the previous approved version throughout.

## Deployment and evaluation

Deploy the reviewed migration/application first; update both workflow and
application_ref pins in validation repositories to the same full reviewed SHA.
Index reusable workflow accepts optional SARVAM_API_KEY. Without it, overlap pairs
are staged and wait for semantic scanning in Streamlit; no activation bypass occurs.
Existing callers passing only DATABASE_URL continue working with that review boundary.

Existing active versions are not silently re-approved, revoked or rewritten during
migration. Run an explicit integrity audit to review legacy content such as OpenBull's
lifecycle descriptions before the next validation. Approved mappings to excluded
sections have no trusted context; analysis fails closed until humans revise mappings
or restore trustworthy documentation through a reviewed update.

Raw scan counts, candidate selection signals, four-way assessments, uncertainty,
diagnostics and human resolutions are retained for evaluation. Live reports show
workflow counts across scans. These are not detection precision/recall. Independently
adjudicated pair labels, including narrowing misses, are still required for accuracy.
No new AI accuracy, cost savings or latency improvement is claimed.
