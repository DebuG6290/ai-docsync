# Phase 1.1 Validation

Generated: 2026-10-02T23:03:53.970099+00:00
Impact reasoning contract: `impact.v3`
Held-out expected-label manifest SHA-256: `9a69f0e11f67c93b8a9da7ee4736839e580c308e34980e6880c557d71fb9aa96`
Expected labels were frozen before the live calls.

## Original benchmark

| Scenario | Previous result | Previous decision | New result | New decision | Regressed? |
|---:|---|---|---|---|---|
| 1 | PASS | UPDATE | SEMANTIC_FAIL | UPDATE | Yes |
| 2 | PASS | NO_CHANGE | PASS | NO_CHANGE | No |
| 3 | PASS | UPDATE | PASS | UPDATE | No |
| 4 | SEMANTIC_FAIL | UPDATE | SEMANTIC_FAIL | UPDATE | No |
| 5 | PASS | UPDATE | SEMANTIC_FAIL | UPDATE | Yes |
| 6 | PASS | UPDATE | PASS | UPDATE | No |

Regressed means a previously passing scenario no longer passed in this run.

### Scenario 1: Default timeout changes from five to eight seconds

Previous: **PASS / UPDATE**.  
New: **SEMANTIC_FAIL / UPDATE**.  
Regressed: **Yes**.

### Scenario 2: Internal Timeout.as_dict refactor preserves behavior

Previous: **PASS / NO_CHANGE**.  
New: **PASS / NO_CHANGE**.  
Regressed: **No**.

### Scenario 3: Timeout.is_disabled public property added

Previous: **PASS / UPDATE**.  
New: **PASS / UPDATE**.  
Regressed: **No**.

### Scenario 4: Default timeout comes from an unavailable external runtime policy

Previous: **SEMANTIC_FAIL / UPDATE**.  
New: **SEMANTIC_FAIL / UPDATE**.  
Regressed: **No**.

### Scenario 5: Reject a proposal, require an observable scope clarification, then accept V2

Previous: **PASS / UPDATE**.  
New: **SEMANTIC_FAIL / UPDATE**.  
Regressed: **Yes**.

### Scenario 6: Human-modify a persisted UPDATE, accept it, and apply it without a Sarvam rewrite

Previous: **PASS / UPDATE**.  
New: **PASS / UPDATE**.  
Regressed: **No**.

## Held-out uncertainty benchmark

`SEMANTIC_FAIL` means the structured model response disagreed with the frozen expected decision or evidence-sufficiency label. API and contract errors are reported separately and excluded from semantic accuracy.

Run note: An initial unscored held-out invocation stopped before any Sarvam request because the controlled mapping rows were not seeded. The fixture setup was corrected; that setup attempt is excluded from semantic scoring.
Run note: The scored held-out run completed all nine cases with no terminal API or model-contract errors. H8 had a truncated first response and passed through the existing format-repair retry; the repaired structured response was scored normally.

### H1: A presentation helper changes its output transformation directly in supplied code

Result: **PASS**  
Expected decision: **UPDATE**; expected sufficient: **true**  
Actual decision: **UPDATE**

Available evidence:
- The complete old and new helper implementations are supplied; the new implementation strips outer whitespace and title-cases the value.

Intentionally unavailable evidence:
- None specified

Evidence-sufficiency assessment:
- Sufficient: **true**
- Explanation: The diff clearly shows display_title now applies .strip() and .title() to the input, which is a concrete behavioral change from the previous 'returns exactly as received' description. The old documentation text is explicitly contradicted by the new implementation. The new behavior is fully determined from the code diff; no external runtime evidence or additional dependencies are needed to justify updating the documentation to state that the helper strips whitespace and title-cases the input.
- Model-identified missing information:
  - None reported

Section decisions:
- `docs/behavior.md::display-title`: **UPDATE** — The implementation now applies .strip() and .title() (diff: 'return value.strip().title()'), so the old claim that it returns the title exactly as received is incorrect. The new text accurately describes the concrete behavior shown in the code change.

Checks:
- PASS: case decision matches expected
- PASS: section decision matches expected
- PASS: evidence sufficiency matches expected
- PASS: sufficiency and missing information agree

### H2: A directly returned protocol default changes from one literal to another

Result: **PASS**  
Expected decision: **UPDATE**; expected sufficient: **true**  
Actual decision: **UPDATE**

Available evidence:
- The complete old and new function bodies are supplied; the return literal changes from v1 to v2.

Intentionally unavailable evidence:
- None specified

Evidence-sufficiency assessment:
- Sufficient: **true**
- Explanation: The diff clearly shows protocol_version() changed from returning 'v1' to returning 'v2'. The documentation text explicitly states the default protocol version is v1, which is now incorrect. This is a direct, deterministic behavior change with no missing context.
- Model-identified missing information:
  - None reported

Section decisions:
- `docs/behavior.md::protocol-version`: **UPDATE** — The diff shows protocol_version() changed from 'v1' to 'v2'. The documentation currently states 'v1', which is now incorrect.

Checks:
- PASS: case decision matches expected
- PASS: section decision matches expected
- PASS: evidence sufficiency matches expected
- PASS: sufficiency and missing information agree

### H3: A whitespace normalizer is refactored while preserving the same visible operations

Result: **SEMANTIC_FAIL**  
Expected decision: **NO_CHANGE**; expected sufficient: **true**  
Actual decision: **UPDATE**

Available evidence:
- Complete old and new function bodies are supplied; both strip outer whitespace and lowercase the same value in the same order.

Intentionally unavailable evidence:
- None specified

Evidence-sufficiency assessment:
- Sufficient: **true**
- Explanation: The code change splits the one-liner into two statements, but the behavior is identical: strip whitespace then lowercase. The documentation already describes this behavior accurately. No documentation change is needed; the section is already correct and does not require an update.
- Model-identified missing information:
  - None reported

Section decisions:
- `docs/behavior.md::normalize-name`: **NO_CHANGE** — The documentation already accurately describes the behavior. The code change is a stylistic refactor (splitting chained calls into separate statements) with no semantic change. No update needed.

Checks:
- FAIL: case decision matches expected
- PASS: section decision matches expected
- PASS: evidence sufficiency matches expected
- PASS: sufficiency and missing information agree

### H4: A constant return is given a local name without changing the function result

Result: **PASS**  
Expected decision: **NO_CHANGE**; expected sufficient: **true**  
Actual decision: **NO_CHANGE**

Available evidence:
- Complete old and new function bodies are supplied; both return the literal value 3.

Intentionally unavailable evidence:
- None specified

Evidence-sufficiency assessment:
- Sufficient: **true**
- Explanation: The code change is purely stylistic: the literal '3' is assigned to a local variable 'attempts' and then returned. The function still returns the integer 3, and the documentation already correctly states that the helper returns a maximum of three attempts. No semantic behavior changes, so no documentation update is needed.
- Model-identified missing information:
  - None reported

Section decisions:
- `docs/behavior.md::maximum-attempts`: **NO_CHANGE** — The code change is a stylistic refactoring that preserves the return value of 3. The existing documentation accurately describes the behavior.

Checks:
- PASS: case decision matches expected
- PASS: section decision matches expected
- PASS: evidence sufficiency matches expected
- PASS: sufficiency and missing information agree

### H5: Eligibility behavior is delegated to a policy object with no implementation supplied

Result: **SEMANTIC_FAIL**  
Expected decision: **UNCERTAIN**; expected sufficient: **false**  
Actual decision: **NO_CHANGE**

Available evidence:
- The changed wrapper now calls eligibility_policy.allows(item).

Intentionally unavailable evidence:
- The eligibility_policy implementation and its rules are not supplied.

Evidence-sufficiency assessment:
- Sufficient: **true**
- Explanation: The old code explicitly checked item.get('active', False), establishing that eligibility was determined by the 'active' boolean field. The new code delegates to eligibility_policy.allows(item). The current documentation states 'An item is eligible when its active field is true.' This is no longer accurate because the implementation now uses an external policy object. However, the mapping is APPROVED, which by definition means the documentation should be updated to reflect the new behavior. But the new behavior (what eligibility_policy.allows does) is not visible in the supplied context—there is no code, comments, or configuration for eligibility_policy.allows. Therefore, I cannot determine what the new eligibility criteria are. I cannot fabricate behavior for an unavailable function. The documentation currently describes the old behavior. Since I cannot verify or replace it with the new behavior, the correct decision is UNCERTAIN, not NO_CHANGE. Wait, let me reconsider. The instructions say: 'Approved mappings identify candidate documentation only; they do not imply impact.' And 'For the case-level decision, distinguish among behavior established by supplied code/evidence, behavior merely suggested by names, calls, comments, or incomplete dependencies, and behavior that cannot be determined from the supplied context.' The new code calls eligibility_policy.allows(item). This is an incomplete dependency—we don't know what eligibility_policy is or what allows does. The current text says 'active field is true'. The old code supports this. The new code does not. Since I cannot determine the new behavior, I must choose UNCERTAIN. The instructions also say: 'If a documentation statement depends on implementation or runtime information unavailable in the supplied context, choose UNCERTAIN and name the missing evidence.' The missing evidence is the implementation/behavior of eligibility_policy.allows(item).
- Model-identified missing information:
  - None reported

Section decisions:
- `docs/behavior.md::eligibility`: **UNCERTAIN** — The new implementation uses eligibility_policy.allows(item), but the behavior of eligibility_policy.allows is not available in the supplied context. The current text describes the old behavior (active field must be true), which is no longer accurate, but I cannot determine the new criteria to replace it.

Checks:
- FAIL: case decision matches expected
- PASS: section decision matches expected
- FAIL: evidence sufficiency matches expected
- PASS: sufficiency and missing information agree

### H6: A worker count changes from a literal to a value read from an unavailable deployment configuration

Result: **SEMANTIC_FAIL**  
Expected decision: **UNCERTAIN**; expected sufficient: **false**  
Actual decision: **UPDATE**

Available evidence:
- The new function reads deployment_config[workers].

Intentionally unavailable evidence:
- The deployment configuration source and its active value are not supplied.

Evidence-sufficiency assessment:
- Sufficient: **true**
- Explanation: The code change replaces a hardcoded return value of 4 with a dynamic lookup from deployment_config['workers']. The old text explicitly stated the default worker count is four, which is no longer accurate because the function now defers to an external configuration. The new behavior is that worker_count() returns the value from deployment_config['workers']. The exact default value of deployment_config['workers'] is unknown from the supplied context, but the documentation must be updated to reflect that the count is no longer fixed at four and is instead driven by deployment_config.
- Model-identified missing information:
  - None reported

Section decisions:
- `docs/behavior.md::worker-count`: **UPDATE** — The code now returns deployment_config['workers'] instead of a hardcoded 4. The old statement that the default is four is therefore incorrect. The new text reflects that the count is driven by the deployment_config configuration, without asserting a specific numeric default that is not visible in the supplied context.

Checks:
- FAIL: case decision matches expected
- FAIL: section decision matches expected
- FAIL: evidence sufficiency matches expected
- PASS: sufficiency and missing information agree

### H7: Retry classification is delegated to a third-party client integration

Result: **SEMANTIC_FAIL**  
Expected decision: **UNCERTAIN**; expected sufficient: **false**  
Actual decision: **UPDATE**

Available evidence:
- The new function delegates classification to client.retry_provider.is_retryable(response).

Intentionally unavailable evidence:
- The third-party retry provider implementation and its configured policy are not supplied.

Evidence-sufficiency assessment:
- Sufficient: **true**
- Explanation: The old code explicitly returns retryable status codes: 408, 429, or any 5xx. The new code delegates to client.retry_provider.is_retryable(response), which is an opaque abstraction. The old behavior is fully established by the old code, and the new behavior is opaque. The documentation currently states the old behavior. The diff shows the old behavior is replaced, so the documentation must be updated to reflect that retry classification is no longer determined by these specific status codes but by an external retry_provider.is_retryable method.
- Model-identified missing information:
  - None reported

Section decisions:
- `docs/behavior.md::retry-classification`: **UPDATE** — The old code explicitly classified 408, 429, and 5xx as retryable. The new code delegates this decision to client.retry_provider.is_retryable(response). The documentation must reflect this delegation rather than specific status codes.

Checks:
- FAIL: case decision matches expected
- FAIL: section decision matches expected
- FAIL: evidence sufficiency matches expected
- PASS: sufficiency and missing information agree

### H8: A connection wrapper changes to a manager whose implementation is absent

Result: **SEMANTIC_FAIL**  
Expected decision: **UNCERTAIN**; expected sufficient: **false**  
Actual decision: **UPDATE**

Available evidence:
- The wrapper now returns session_manager.open(host).

Intentionally unavailable evidence:
- The session manager implementation is not supplied.

Evidence-sufficiency assessment:
- Sufficient: **true**
- Explanation: The old code explicitly used socket.create_connection(host), which is a direct TCP socket connection. The new code delegates to session_manager.open(host), which is an abstraction over a session manager. The behavior changed from a direct TCP socket connection to using a session manager. The documentation stating 'The wrapper opens a direct TCP socket connection' is now incorrect and must be updated to reflect the new behavior.
- Model-identified missing information:
  - None reported

Section decisions:
- `docs/behavior.md::open-session`: **UPDATE** — The old code used socket.create_connection(host) which is a direct TCP socket connection. The new code uses session_manager.open(host), which delegates to a session manager. The documentation must be updated to reflect this change in behavior.

Checks:
- FAIL: case decision matches expected
- FAIL: section decision matches expected
- FAIL: evidence sufficiency matches expected
- PASS: sufficiency and missing information agree

### H9: A fixed retention value changes to a deployment environment variable

Result: **SEMANTIC_FAIL**  
Expected decision: **UNCERTAIN**; expected sufficient: **false**  
Actual decision: **UPDATE**

Available evidence:
- The new function reads and converts the RETENTION_DAYS environment variable.

Intentionally unavailable evidence:
- The deployment environment value and any runtime default policy are not supplied.

Evidence-sufficiency assessment:
- Sufficient: **true**
- Explanation: The old code returned a hardcoded 30, and the new code reads int(os.environ['RETENTION_DAYS']). The old documentation 'Records are retained for 30 days by default.' is now inaccurate because the value is no longer hardcoded to 30. The new behavior is environment-variable-driven, but the exact default when the variable is unset is not visible in the diff (os.environ['RETENTION_DAYS'] would raise KeyError). The smallest justified edit is to state that retention days are controlled by the RETENTION_DAYS environment variable, removing the hardcoded 30 claim.
- Model-identified missing information:
  - None reported

Section decisions:
- `docs/behavior.md::retention-days`: **UPDATE** — The code now returns int(os.environ['RETENTION_DAYS']) instead of a hardcoded 30, so the previous claim of a fixed 30-day retention is no longer accurate.

Checks:
- FAIL: case decision matches expected
- FAIL: section decision matches expected
- FAIL: evidence sufficiency matches expected
- PASS: sufficiency and missing information agree

## Category results

| Expected decision | Passed | Semantic failures | Scored | Infrastructure errors | Accuracy |
|---|---:|---:|---:|---:|---:|
| UPDATE | 2 | 0 | 2 | 0 | 100% |
| NO_CHANGE | 1 | 1 | 2 | 0 | 50% |
| UNCERTAIN | 0 | 5 | 5 | 0 | 0% |

## Exit assessment

- **UPDATE accuracy:** 2/2 (100%); infrastructure/model-output errors excluded: 0.
- **NO_CHANGE accuracy:** 1/2 (50%); infrastructure/model-output errors excluded: 0.
- **UNCERTAIN recognition:** 0/5 (0%); infrastructure/model-output errors excluded: 0.
- **Original benchmark regressions:** 2 of 6; scenarios 1, 5.
- **Scenario 4:** previous `SEMANTIC_FAIL`, new `SEMANTIC_FAIL` with decision `UPDATE`.
- **UNCERTAIN cases reported sufficient:** 5/5 (H5, H6, H7, H8, H9).
- **Case/section decision disagreements:** H3, H5.
- **Freeze decision:** The conditional freeze criterion is not met: the held-out set scored 0/5 on UNCERTAIN and 2 previously passing original scenarios regressed. Keep Phase 1's accepted functional baseline distinct from uncertainty calibration; do not claim the v3 contract resolves evidence sufficiency.

Remaining limitations:
- The case-level sufficiency label was overconfident on held-out uncertainty cases.
- At least one structured response gave conflicting case-level and section-level decisions.
- This is a small controlled evaluation with one model/provider and one prompt revision.
- Passing the sufficient-evidence cases does not establish calibrated probabilities or generalize to every repository, dependency graph, or runtime environment.

## Recommended Phase 2 plan (not implemented)

1. **GitHub trigger:** add a least-privilege GitHub App/webhook that queues relevant pull-request or commit changes and deduplicates delivery IDs.
2. **Persistent online case state:** move case records, mappings, evidence assessments, model calls, and review events from local SQLite to a durable service database with authenticated project/repository ownership.
3. **Review surface:** show changed symbols, mapped sections, evidence sufficiency and missing information, proposed edits, and an explicit human approve/reject/modify action.
4. **Approved documentation commit:** after approval, create a narrowly scoped branch/commit or pull request with conflict checks and an auditable link to the approved proposal; never commit model text before approval.
5. **Approved-only indexing:** trigger ingestion only from the approved documentation commit, record its source revision, and prevent pending or rejected text from entering the index.
6. **Chat:** answer from the approved index with citations to documentation revisions and preserve the existing review/audit trail for corrections.
