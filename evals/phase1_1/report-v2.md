# Phase 1.1 Validation Results

Generated: 2026-10-02T23:48:58.657935+00:00
Impact reasoning contract: `impact.v4 / revision.v3`
The original-six expectations were hash-checked before their rerun. Held-out labels, rationales, and fixture commit IDs were hash-checked before the held-out calls; none changed after held-out output. Proposal reviews were completed against those frozen rubrics.

Run notes:
- The original six were run once against original_expectations.json; the independent held-out manifest did not enter their model prompts.
- All 11 held-out cases were called once after the final labels and fixture commits passed SHA-256 preflight. H5-H11 labels were not revised after this run.
- Scenario 5's saved V2 text was re-scored offline after replacing a phrase-only deadline check with a generic negated-total-duration check; no Sarvam call was repeated.
- The proposal-presence check is evaluated against the model's actual section decision, while expected-decision correctness is scored separately.

## Original benchmark

| Scenario | Previous Phase 1.1 result | Previous decision | New result | New decision | Regression vs accepted Phase 1 baseline? |
|---:|---|---|---|---|---|
| 1 | SEMANTIC_FAIL | UPDATE | PASS | UPDATE | No |
| 2 | PASS | NO_CHANGE | PASS | NO_CHANGE | No |
| 3 | PASS | UPDATE | PASS | UPDATE | No |
| 4 | SEMANTIC_FAIL | UPDATE | SEMANTIC_FAIL | UPDATE | Not comparable |
| 5 | SEMANTIC_FAIL | UPDATE | SEMANTIC_FAIL | UPDATE | No |
| 6 | PASS | UPDATE | PASS | UPDATE | No |

Previous Phase 1.1 failures for Scenarios 1 and 5 are diagnosed explicitly below. Scenario 4's expected result changed from UNCERTAIN to UPDATE/PARTIAL under the frozen new definition, so its old and new pass labels are not directly comparable.

### Scenario 1: Default timeout changes from five to eight seconds

Previous: **SEMANTIC_FAIL / UPDATE**; accepted Phase 1 baseline: **PASS**; new: **PASS / UPDATE**.
Regression: **False**.
Frozen label rationale: The pinned source directly changes the configured default from 5 to 8. Each mapped section contains a stale five-second default claim, including the client-example comment; all three sections should change.

Previous failed-check diagnosis:
- The prior Phase 1.1 response returned UPDATE at case level, but its client-default section was NO_CHANGE and its QuickStart section was NO_CHANGE; both section checks failed.

Sections:
- `docs/advanced/timeouts.md::__intro__` — expected **UPDATE / COMPLETE**, actual **UPDATE / COMPLETE**.
  Reason: The old text states the default is 5 seconds. The code changed the default to 8.0. This is a direct, factual update with no unsupported claims.
  Missing information: []
  Safe claims: ["DEFAULT_TIMEOUT_CONFIG is set to Timeout(timeout=8.0) in httpx/_config.py."]
  Unsupported claims: []

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of
  network inactivity.
  ```
  Proposal review: The changed eight-second value is supported; network-inactivity wording is preserved from the unchanged approved section.
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client` — expected **UPDATE / COMPLETE**, actual **UPDATE / COMPLETE**.
  Reason: The example comment for the default client now reflects the new default of 8 seconds. This is the smallest useful edit to keep the example accurate.
  Missing information: []
  Safe claims: ["DEFAULT_TIMEOUT_CONFIG is set to Timeout(timeout=8.0) in httpx/_config.py."]
  Unsupported claims: []

  Proposed text:

  ```markdown
  ## Setting a default timeout on a client
  
  You can set a timeout on a client instance, which results in the given
  `timeout` being used as the default for requests made with this client:
  
  ```python
  client = httpx.Client()              # Use a default 8s timeout everywhere.
  client = httpx.Client(timeout=10.0)  # Use a default 10s timeout everywhere.
  client = httpx.Client(timeout=None)  # Disable all timeouts by default.
  ```
  ```
  Proposal review: The default example changes to eight seconds, matching the directly changed constant. Other explicit examples are preserved.
- `docs/quickstart.md::timeouts` — expected **UPDATE / COMPLETE**, actual **UPDATE / COMPLETE**.
  Reason: The old text states the default is five seconds. The code changed the default to 8.0. This is a direct, factual update with no unsupported claims.
  Missing information: []
  Safe claims: ["DEFAULT_TIMEOUT_CONFIG is set to Timeout(timeout=8.0) in httpx/_config.py."]
  Unsupported claims: []

  Proposed text:

  ```markdown
  ## Timeouts
  
  HTTPX defaults to including reasonable timeouts for all network operations,
  meaning that if a connection is not properly established then it should always
  raise an error rather than hanging indefinitely.
  
  The default timeout for network inactivity is eight seconds. You can modify the
  value to be more or less strict:
  
  ```pycon
  >>> httpx.get('https://github.com/', timeout=0.001)
  ```
  
  You can also disable the timeout behavior completely...
  
  ```pycon
  >>> httpx.get('https://github.com/', timeout=None)
  ```
  
  For advanced timeout management, see [Timeout fine-tuning](advanced/timeouts.md#fine-tuning-the-configuration).
  ```
  Proposal review: The default changes to eight seconds; the existing network-inactivity scope is preserved.

Checks:
- PASS: returned exactly the mapped section IDs
- PASS: case workflow state matches frozen expected aggregation
- PASS: application workflow state matches section decisions
- PASS: section decision correct: docs/advanced/timeouts.md::__intro__
- PASS: evidence completeness correct: docs/advanced/timeouts.md::__intro__
- PASS: section decision correct: docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client
- PASS: evidence completeness correct: docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client
- PASS: section decision correct: docs/quickstart.md::timeouts
- PASS: evidence completeness correct: docs/quickstart.md::timeouts
- PASS: proposals exist exactly for UPDATE sections
- PASS: proposal review 1|docs/advanced/timeouts.md::__intro__: safe claims are supported by supplied evidence
- PASS: proposal review 1|docs/advanced/timeouts.md::__intro__: proposed facts are supported by safe_claims
- PASS: proposal review 1|docs/advanced/timeouts.md::__intro__: no unsupported claim is asserted
- PASS: proposal review 1|docs/advanced/timeouts.md::__intro__: frozen claim rubric is satisfied
- PASS: proposal review 1|docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client: safe claims are supported by supplied evidence
- PASS: proposal review 1|docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client: proposed facts are supported by safe_claims
- PASS: proposal review 1|docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client: no unsupported claim is asserted
- PASS: proposal review 1|docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client: frozen claim rubric is satisfied
- PASS: proposal review 1|docs/quickstart.md::timeouts: safe claims are supported by supplied evidence
- PASS: proposal review 1|docs/quickstart.md::timeouts: proposed facts are supported by safe_claims
- PASS: proposal review 1|docs/quickstart.md::timeouts: no unsupported claim is asserted
- PASS: proposal review 1|docs/quickstart.md::timeouts: frozen claim rubric is satisfied

### Scenario 2: Internal Timeout.as_dict refactor preserves behavior

Previous: **PASS / NO_CHANGE**; accepted Phase 1 baseline: **PASS**; new: **PASS / NO_CHANGE**.
Regression: **False**.
Frozen label rationale: The complete old/new method bodies return the same mapping values; the documented behavior remains accurate.

Sections:
- `docs/advanced/timeouts.md::fine-tuning-the-configuration` — expected **NO_CHANGE / COMPLETE**, actual **NO_CHANGE / COMPLETE**.
  Reason: The code change only refactors the implementation of `Timeout.as_dict()` to use a dictionary comprehension instead of a literal dictionary. This does not alter the behavior, return type, or semantics of the method. The documentation describes the conceptual timeout types and how to configure them, which remains unchanged. No useful replacement is needed.
  Missing information: []
  Safe claims: ["The `as_dict` method returns a dictionary mapping 'connect', 'read', 'write', and 'pool' to their respective timeout values.", "The method signature is `def as_dict(self) -> dict[str, float | None]`."]
  Unsupported claims: []

Checks:
- PASS: returned exactly the mapped section IDs
- PASS: case workflow state matches frozen expected aggregation
- PASS: application workflow state matches section decisions
- PASS: section decision correct: docs/advanced/timeouts.md::fine-tuning-the-configuration
- PASS: evidence completeness correct: docs/advanced/timeouts.md::fine-tuning-the-configuration
- PASS: proposals exist exactly for UPDATE sections

### Scenario 3: Timeout.is_disabled public property added

Previous: **PASS / UPDATE**; accepted Phase 1 baseline: **PASS**; new: **PASS / UPDATE**.
Regression: **False**.
Frozen label rationale: The added property and its full implementation are supplied; the candidate section does not document this public property.

Sections:
- `docs/advanced/timeouts.md::setting-and-disabling-timeouts` — expected **UPDATE / COMPLETE**, actual **UPDATE / COMPLETE**.
  Reason: The code adds `Timeout.is_disabled` which returns `True` when all timeout values are `None`, matching the documented behavior of `timeout=None`. The current text does not mention this property, so it should be updated to describe it. The evidence is COMPLETE because the new property's implementation is fully visible in the code.
  Missing information: []
  Safe claims: ["The `is_disabled` property returns `True` when all timeout values are `None`", "The `is_disabled` property is a read-only property on `Timeout` instances", "The `is_disabled` property uses `as_dict()` to check all timeout values"]
  Unsupported claims: ["The `is_disabled` property is used in the public API for any specific purpose", "The `is_disabled` property affects runtime behavior beyond its return value", "The `is_disabled` property is documented in any other section"]

  Proposed text:

  ```markdown
  ## Setting and disabling timeouts
  
  You can set timeouts for an individual request:
  
  ```python
  # Using the top-level API:
  httpx.get('http://example.com/api/v1/example', timeout=10.0)
  
  # Using a client instance:
  with httpx.Client() as client:
      client.get("http://example.com/api/v1/example", timeout=10.0)
  ```
  
  Or disable timeouts for an individual request:
  
  ```python
  # Using the top-level API:
  httpx.get('http://example.com/api/v1/example', timeout=None)
  
  # Using a client instance:
  with httpx.Client() as client:
      client.get("http://example.com/api/v1/example", timeout=None)
  ```
  
  You can also check whether a `Timeout` instance has all timeouts disabled via the `is_disabled` property:
  
  ```python
  timeout = Timeout(None)
  assert timeout.is_disabled
  ```
  ```
  Proposal review: The new is_disabled behavior and example match the supplied property implementation; existing section behavior is retained.

Checks:
- PASS: returned exactly the mapped section IDs
- PASS: case workflow state matches frozen expected aggregation
- PASS: application workflow state matches section decisions
- PASS: section decision correct: docs/advanced/timeouts.md::setting-and-disabling-timeouts
- PASS: evidence completeness correct: docs/advanced/timeouts.md::setting-and-disabling-timeouts
- PASS: proposals exist exactly for UPDATE sections
- PASS: proposal documents is_disabled
- PASS: proposal review 3|docs/advanced/timeouts.md::setting-and-disabling-timeouts: safe claims are supported by supplied evidence
- PASS: proposal review 3|docs/advanced/timeouts.md::setting-and-disabling-timeouts: proposed facts are supported by safe_claims
- PASS: proposal review 3|docs/advanced/timeouts.md::setting-and-disabling-timeouts: no unsupported claim is asserted
- PASS: proposal review 3|docs/advanced/timeouts.md::setting-and-disabling-timeouts: frozen claim rubric is satisfied

### Scenario 4: Default timeout comes from an unavailable external runtime policy

Previous: **SEMANTIC_FAIL / UPDATE**; accepted Phase 1 baseline: **SEMANTIC_FAIL**; new: **SEMANTIC_FAIL / UPDATE**.
Regression: **None**.
Frozen label rationale: The supplied diff directly replaces the literal default with a call to the imported runtime policy, so a useful bounded update can describe that source. The policy implementation and numeric runtime value are unavailable, so no section may continue to assert a specific duration as established fact. This scenario is re-labeled under the explicit UPDATE/PARTIAL definition; no numeric policy output is assumed.

Sections:
- `docs/advanced/timeouts.md::__intro__` — expected **UPDATE / PARTIAL**, actual **UPDATE / COMPLETE**.
  Reason: The old code hardcoded 5.0; the new code calls timeout_seconds(). The text should reflect the source of the default value without inventing a specific numeric value. The `timeout_seconds()` call is directly visible in the code diff.
  Missing information: []
  Safe claims: ["The default timeout value is now obtained by calling timeout_seconds()", "timeout_seconds() is imported from external_runtime_policy"]
  Unsupported claims: ["The numeric value returned by timeout_seconds() is 5 seconds", "timeout_seconds() is a function in the httpx package"]

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after `timeout_seconds()` seconds of
  network inactivity.
  ```
  Proposal review: The safe claim establishes that the default comes from timeout_seconds(), but not that the returned value is measured in seconds. The proposal's 'timeout_seconds() seconds' adds that unsupported unit assertion.
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client` — expected **UPDATE / PARTIAL**, actual **UPDATE / COMPLETE**.
  Reason: The code change does not affect the client-level timeout API; the default for client() without an explicit timeout now comes from the updated DEFAULT_TIMEOUT_CONFIG. The examples remain valid, but the comment on the first example should be updated to avoid implying a fixed 5s default. The smallest useful edit is to change the comment.
  Missing information: []
  Safe claims: ["The default timeout for client() is now determined by the updated DEFAULT_TIMEOUT_CONFIG", "The client constructor still accepts timeout=10.0 and timeout=None"]
  Unsupported claims: ["The default timeout is 5 seconds", "The default timeout is configurable at runtime via external_runtime_policy"]

  Proposed text:

  ```markdown
  ## Setting a default timeout on a client
  
  You can set a timeout on a client instance, which results in the given
  `timeout` being used as the default for requests made with this client:
  
  ```python
  client = httpx.Client()              # Use a default timeout everywhere.
  client = httpx.Client(timeout=10.0)  # Use a default 10s timeout everywhere.
  client = httpx.Client(timeout=None)  # Disable all timeouts by default.
  ```
  ```
  Proposal review: The proposal removes the stale fixed duration safely but does not document the supported source of the no-argument default required by the frozen rubric.
- `docs/quickstart.md::timeouts` — expected **UPDATE / PARTIAL**, actual **UPDATE / COMPLETE**.
  Reason: The old text states 'The default timeout for network inactivity is five seconds.' The new code uses timeout_seconds(). We should update the text to say the default is timeout_seconds() without inventing a numeric value. The rest of the section is unchanged.
  Missing information: []
  Safe claims: ["The default timeout value is now obtained by calling timeout_seconds()", "timeout_seconds() is imported from external_runtime_policy"]
  Unsupported claims: ["The numeric value returned by timeout_seconds() is 5 seconds", "timeout_seconds() is a function in the httpx package"]

  Proposed text:

  ```markdown
  ## Timeouts
  
  HTTPX defaults to including reasonable timeouts for all network operations,
  meaning that if a connection is not properly established then it should always
  raise an error rather than hanging indefinitely.
  
  The default timeout for network inactivity is `timeout_seconds()`. You can modify the
  value to be more or less strict:
  
  ```pycon
  >>> httpx.get('https://github.com/', timeout=0.001)
  ```
  
  You can also disable the timeout behavior completely...
  
  ```pycon
  >>> httpx.get('https://github.com/', timeout=None)
  ```
  
  For advanced timeout management, see [Timeout fine-tuning](advanced/timeouts.md#fine-tuning-the-configuration).
  ```
  Proposal review: The text identifies timeout_seconds() as the default source and does not assert its runtime value or a numeric duration.

Checks:
- PASS: returned exactly the mapped section IDs
- PASS: case workflow state matches frozen expected aggregation
- PASS: application workflow state matches section decisions
- PASS: section decision correct: docs/advanced/timeouts.md::__intro__
- FAIL: evidence completeness correct: docs/advanced/timeouts.md::__intro__
- PASS: section decision correct: docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client
- FAIL: evidence completeness correct: docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client
- PASS: section decision correct: docs/quickstart.md::timeouts
- FAIL: evidence completeness correct: docs/quickstart.md::timeouts
- PASS: proposals exist exactly for UPDATE sections
- PASS: proposal review 4|docs/advanced/timeouts.md::__intro__: safe claims are supported by supplied evidence
- FAIL: proposal review 4|docs/advanced/timeouts.md::__intro__: proposed facts are supported by safe_claims
- FAIL: proposal review 4|docs/advanced/timeouts.md::__intro__: no unsupported claim is asserted
- FAIL: proposal review 4|docs/advanced/timeouts.md::__intro__: frozen claim rubric is satisfied
- PASS: proposal review 4|docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client: safe claims are supported by supplied evidence
- PASS: proposal review 4|docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client: proposed facts are supported by safe_claims
- PASS: proposal review 4|docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client: no unsupported claim is asserted
- FAIL: proposal review 4|docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client: frozen claim rubric is satisfied
- PASS: proposal review 4|docs/quickstart.md::timeouts: safe claims are supported by supplied evidence
- PASS: proposal review 4|docs/quickstart.md::timeouts: proposed facts are supported by safe_claims
- PASS: proposal review 4|docs/quickstart.md::timeouts: no unsupported claim is asserted
- PASS: proposal review 4|docs/quickstart.md::timeouts: frozen claim rubric is satisfied

Failed checks: evidence completeness correct: docs/advanced/timeouts.md::__intro__, evidence completeness correct: docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client, evidence completeness correct: docs/quickstart.md::timeouts, proposal review 4|docs/advanced/timeouts.md::__intro__: proposed facts are supported by safe_claims, proposal review 4|docs/advanced/timeouts.md::__intro__: no unsupported claim is asserted, proposal review 4|docs/advanced/timeouts.md::__intro__: frozen claim rubric is satisfied, proposal review 4|docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client: frozen claim rubric is satisfied

### Scenario 5: Reject a proposal, require an observable scope clarification, then accept V2

Previous: **SEMANTIC_FAIL / UPDATE**; accepted Phase 1 baseline: **PASS**; new: **SEMANTIC_FAIL / UPDATE**.
Regression: **False**.

Previous failed-check diagnosis:
- The prior V2 text stated that the timeout does not represent an overall deadline for the complete HTTP request; the old phrase detector omitted 'does not represent', so only the 'requested feedback appears in V2' check failed.

Sections:
- `docs/advanced/timeouts.md::__intro__` — expected **n/a / n/a**, actual **UPDATE / n/a**.
  Reason: The reviewer rejected the proposal because it did not explicitly clarify that the timeout is for network inactivity, not an overall deadline for the complete HTTP request. The revised text adds this clarification while keeping the factual update from 5 to 8 seconds.
  Missing information: []
  Safe claims: []
  Unsupported claims: []

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of network inactivity. This timeout applies to periods when no data is being transmitted, not to the total duration of the request.
  ```

Checks:
- PASS: revision_checks: V1 preserved
- PASS: revision_checks: rejection event and exact reason preserved
- PASS: revision_checks: V2 differs from V1
- PASS: revision_checks: requested feedback appears in V2
- PASS: revision_checks: only rejected proposal gained a version
- PASS: revision_checks: V2 explicitly accepted
- PASS: Scenario 5 revised proposal: safe claims are supported by supplied evidence
- FAIL: Scenario 5 revised proposal: proposed facts are supported by safe_claims
- FAIL: Scenario 5 revised proposal: no unsupported claim is asserted
- PASS: Scenario 5 revised proposal: frozen claim rubric is satisfied

Failed checks: Scenario 5 revised proposal: proposed facts are supported by safe_claims, Scenario 5 revised proposal: no unsupported claim is asserted

Scenario 5 HITL checks:
- PASS: V1 preserved
- PASS: rejection event and exact reason preserved
- PASS: V2 differs from V1
- PASS: requested feedback appears in V2
- PASS: only rejected proposal gained a version
- PASS: V2 explicitly accepted

Revision evidence completeness: **COMPLETE**
Revision safe claims: ["DEFAULT_TIMEOUT_CONFIG is set to Timeout(timeout=8.0) in httpx/_config.py.", "The timeout value was changed from 5.0 to 8.0."]
Revision unsupported claims: []
Manual proposal review: The V2 includes the requested semantic clarification, so the HITL feedback check passes. Its new statement that the timeout does not govern total request duration is absent from the revision's safe_claims and supplied code evidence; the network-inactivity phrase was already in approved text, but this new guarantee was not established there.

### Scenario 6: Human-modify a persisted UPDATE, accept it, and apply it without a Sarvam rewrite

Previous: **PASS / UPDATE**; accepted Phase 1 baseline: **PASS**; new: **PASS / UPDATE**.
Regression: **False**.

Sections:
- `docs/advanced/timeouts.md::__intro__` — expected **n/a / n/a**, actual **UPDATE / n/a**.
  Reason: 
  Missing information: []
  Safe claims: []
  Unsupported claims: []

  Proposed text:

  ```markdown
  The default timeout is 8 seconds of network inactivity.
  
  This setting does not impose an overall deadline for the complete HTTP request.
  ```

Checks:
- PASS: revision_checks: human-authored version stored exactly
- PASS: revision_checks: no Sarvam rewrite during review
- PASS: revision_checks: human version explicitly accepted
- PASS: apply_checks: apply command succeeded
- PASS: apply_checks: exact human text appears in documentation
- PASS: apply_checks: applied version is the human version
- PASS: apply_checks: section hash recorded
- PASS: apply_checks: file hash recorded
- PASS: apply_checks: no Sarvam calls for human edit

Scenario 5 HITL checks:
- PASS: human-authored version stored exactly
- PASS: no Sarvam rewrite during review
- PASS: human version explicitly accepted

Scenario 6 HITL/apply checks:
- PASS: apply command succeeded
- PASS: exact human text appears in documentation
- PASS: applied version is the human version
- PASS: section hash recorded
- PASS: file hash recorded
- PASS: no Sarvam calls for human edit

## Held-out uncertainty benchmark

A case is a semantic failure if its frozen section decision, completeness classification, aggregation, claim boundary, proposal safety, or relevant missing-information check fails. Infrastructure errors are listed separately and excluded from semantic accuracy.

### H1: A presentation helper changes its output transformation directly in supplied code

Result: **PASS**
Expected decision/completeness: **UPDATE / COMPLETE**; actual: **UPDATE / COMPLETE**.
Expected missing information: []
Model-identified missing information: []

Available evidence:
- The complete old and new helper implementations are supplied; the new implementation strips outer whitespace and title-cases the value.

Intentionally unavailable evidence:
- None specified

Adjudication: UPDATE is appropriate because the old text says the input is returned exactly, while the new complete implementation directly changes both whitespace and casing. The replacement can state only those two visible transformations.
Model explanation: The old text claims the title is returned exactly as received, but the code now applies `.strip()` and `.title()`. A bounded, directly supported update is possible without inventing downstream behavior.
Safe claims: ["The function returns value.strip().title()", "The function is named display_title"]
Unsupported claims: []

Proposed text:

```markdown
## Display title

The display helper strips leading and trailing whitespace from the supplied title and converts it to title case.
```
Proposal review: The proposal's strip and title-case transformations are visible in the complete new function.

Checks:
- PASS: section decision matches frozen label
- PASS: evidence completeness matches frozen label
- PASS: missing information agrees with completeness
- PASS: safe claims supplied for UPDATE
- PASS: proposed text exists only for UPDATE
- PASS: section result contains the requested section exactly once
- PASS: application aggregation matches returned section decisions
- PASS: workflow state matches the frozen section label
- PASS: proposal review: safe claims are supported by supplied evidence
- PASS: proposal review: proposed facts are supported by safe_claims
- PASS: proposal review: no unsupported claim is asserted
- PASS: proposal review: frozen claim rubric is satisfied
- PASS: proposal review: missing information covers frozen evidence gaps

### H2: A directly returned protocol default changes from one literal to another

Result: **PASS**
Expected decision/completeness: **UPDATE / COMPLETE**; actual: **UPDATE / COMPLETE**.
Expected missing information: []
Model-identified missing information: []

Available evidence:
- The complete old and new function bodies are supplied; the return literal changes from v1 to v2.

Intentionally unavailable evidence:
- None specified

Adjudication: UPDATE is appropriate because the documented default literal is directly contradicted by the new function body. No downstream protocol behavior is inferred.
Model explanation: The function now returns 'v2', so the documented default must be updated. This is the smallest useful edit preserving style.
Safe claims: ["The protocol_version function returns 'v2' in the current code."]
Unsupported claims: ["The default protocol version in all contexts is v2.", "The change is intentional and not a temporary/experimental value."]

Proposed text:

```markdown
## Protocol version

The default protocol version is v2.
```
Proposal review: The complete function directly returns v2; the proposal does not generalize to all protocol implementations.

Checks:
- PASS: section decision matches frozen label
- PASS: evidence completeness matches frozen label
- PASS: missing information agrees with completeness
- PASS: safe claims supplied for UPDATE
- PASS: proposed text exists only for UPDATE
- PASS: section result contains the requested section exactly once
- PASS: application aggregation matches returned section decisions
- PASS: workflow state matches the frozen section label
- PASS: proposal review: safe claims are supported by supplied evidence
- PASS: proposal review: proposed facts are supported by safe_claims
- PASS: proposal review: no unsupported claim is asserted
- PASS: proposal review: frozen claim rubric is satisfied
- PASS: proposal review: missing information covers frozen evidence gaps

### H3: A whitespace normalizer is refactored while preserving the same visible operations

Result: **PASS**
Expected decision/completeness: **NO_CHANGE / COMPLETE**; actual: **NO_CHANGE / COMPLETE**.
Expected missing information: []
Model-identified missing information: []

Available evidence:
- Complete old and new function bodies are supplied; both strip outer whitespace and lowercase the same value in the same order.

Intentionally unavailable evidence:
- None specified

Adjudication: NO_CHANGE is appropriate because the complete old and new bodies establish the same two operations in the same order, matching the current text.
Model explanation: The documentation accurately describes the behavior: the function removes outer whitespace and lowercases the value. The diff shows a pure refactoring with no semantic change; the same operations are performed in the same order. No useful replacement is needed.
Safe claims: ["The function strips outer whitespace from the input value.", "The function lowercases the resulting value.", "The order of operations is strip then lower."]
Unsupported claims: []

Checks:
- PASS: section decision matches frozen label
- PASS: evidence completeness matches frozen label
- PASS: missing information agrees with completeness
- PASS: safe claims supplied for UPDATE
- PASS: proposed text exists only for UPDATE
- PASS: section result contains the requested section exactly once
- PASS: application aggregation matches returned section decisions
- PASS: workflow state matches the frozen section label

### H4: A constant return is given a local name without changing the function result

Result: **PASS**
Expected decision/completeness: **NO_CHANGE / COMPLETE**; actual: **NO_CHANGE / COMPLETE**.
Expected missing information: []
Model-identified missing information: []

Available evidence:
- Complete old and new function bodies are supplied; both return the literal value 3.

Intentionally unavailable evidence:
- None specified

Adjudication: NO_CHANGE is appropriate because both complete implementations return the same integer and the documentation remains accurate.
Model explanation: The current text accurately describes the function's behavior: it returns a maximum of three attempts. The refactoring to introduce a local variable `attempts = 3` does not change the returned value or the semantic meaning. The evidence is complete and supports the existing statement.
Safe claims: ["The function max_attempts returns the value 3.", "The function max_attempts is defined in scenario.py."]
Unsupported claims: []

Checks:
- PASS: section decision matches frozen label
- PASS: evidence completeness matches frozen label
- PASS: missing information agrees with completeness
- PASS: safe claims supplied for UPDATE
- PASS: proposed text exists only for UPDATE
- PASS: section result contains the requested section exactly once
- PASS: application aggregation matches returned section decisions
- PASS: workflow state matches the frozen section label

### H5: Eligibility behavior is delegated to a policy object with no implementation supplied

Result: **SEMANTIC_FAIL**
Expected decision/completeness: **UNCERTAIN / INSUFFICIENT**; actual: **UPDATE / COMPLETE**.
Expected missing information: ["eligibility_policy.allows implementation and rule", "whether the active-field criterion remains true"]
Model-identified missing information: []

Available evidence:
- The changed wrapper now calls eligibility_policy.allows(item).

Intentionally unavailable evidence:
- The eligibility_policy implementation and its rules are not supplied.

Adjudication: UNCERTAIN is appropriate because the current user-facing active-field rule may still be implemented by the unavailable policy. The visible delegation fact is safe, but replacing the eligibility criterion with only an implementation-call description would not resolve this section's behavioral question. The policy implementation is needed to know whether the existing text remains accurate or to write a useful behavioral replacement.
Model explanation: The code no longer checks item.get('active', False) directly; it delegates to eligibility_policy.allows(item). The current text is inaccurate and a safe, bounded replacement is available.
Safe claims: ["is_eligible now returns eligibility_policy.allows(item)", "The eligibility check is delegated to eligibility_policy.allows"]
Unsupported claims: ["The eligibility policy checks the same active field", "The eligibility policy behavior is identical to the previous active-field check"]

Proposed text:

```markdown
## Eligibility

An item is eligible when the eligibility policy allows it.
```
Proposal review: The delegation sentence is literally supported, but it is not a useful answer to whether the active-field rule remains true. The response omits the policy implementation and criterion from missing_information and incorrectly treats the old statement as stale.

Checks:
- FAIL: section decision matches frozen label
- FAIL: evidence completeness matches frozen label
- PASS: missing information agrees with completeness
- PASS: safe claims supplied for UPDATE
- PASS: proposed text exists only for UPDATE
- PASS: section result contains the requested section exactly once
- PASS: application aggregation matches returned section decisions
- FAIL: workflow state matches the frozen section label
- PASS: proposal review: safe claims are supported by supplied evidence
- PASS: proposal review: proposed facts are supported by safe_claims
- PASS: proposal review: no unsupported claim is asserted
- PASS: proposal review: frozen claim rubric is satisfied
- FAIL: proposal review: missing information covers frozen evidence gaps
Failed checks: section decision matches frozen label, evidence completeness matches frozen label, workflow state matches the frozen section label, proposal review: missing information covers frozen evidence gaps

### H6: A worker count changes from a literal to a value read from an unavailable deployment configuration

Result: **PASS**
Expected decision/completeness: **UPDATE / PARTIAL**; actual: **UPDATE / PARTIAL**.
Expected missing information: ["active deployment_config['workers'] value"]
Model-identified missing information: ["Whether deployment_config['workers'] defaults to four at runtime", "Whether deployment_config is mutable or fixed"]

Available evidence:
- The new function reads deployment_config[workers].

Intentionally unavailable evidence:
- The deployment configuration source and its active value are not supplied.

Adjudication: UPDATE is appropriate because the previous section documents the worker count as a fixed default while the changed implementation now reads the value from deployment_config. The source of the value is directly supported; its active/default numeric value is not. A useful replacement can document the configuration source without naming a count.
Model explanation: The code now returns deployment_config['workers'] instead of a hard-coded 4. The documentation should reflect this change to a configuration-driven value while noting the prior default.
Safe claims: ["The function worker_count now returns deployment_config['workers']", "The previous implementation returned a hard-coded constant 4"]
Unsupported claims: ["The default worker count is currently four", "deployment_config['workers'] is set to four by default"]

Proposed text:

```markdown
## Worker count

The worker count is read from the deployment configuration at `deployment_config['workers']`. The previous default value was four.
```
Proposal review: The proposal says the value is read from the configuration key and labels four as the previous value, not the current runtime value.

Checks:
- PASS: section decision matches frozen label
- PASS: evidence completeness matches frozen label
- PASS: missing information agrees with completeness
- PASS: safe claims supplied for UPDATE
- PASS: proposed text exists only for UPDATE
- PASS: section result contains the requested section exactly once
- PASS: application aggregation matches returned section decisions
- PASS: workflow state matches the frozen section label
- PASS: proposal review: safe claims are supported by supplied evidence
- PASS: proposal review: proposed facts are supported by safe_claims
- PASS: proposal review: no unsupported claim is asserted
- PASS: proposal review: frozen claim rubric is satisfied
- PASS: proposal review: missing information covers frozen evidence gaps

### H7: Retry classification is delegated to a third-party client integration

Result: **PASS**
Expected decision/completeness: **UPDATE / PARTIAL**; actual: **UPDATE / PARTIAL**.
Expected missing information: ["retry_provider implementation and configured classification policy"]
Model-identified missing information: ["The exact logic of `client.retry_provider.is_retryable` is not provided in the diff, so we cannot confirm whether 408, 429, and 5xx are still the retryable status codes."]

Available evidence:
- The new function delegates classification to client.retry_provider.is_retryable(response).

Intentionally unavailable evidence:
- The third-party retry provider implementation and its configured policy are not supplied.

Adjudication: UPDATE is appropriate because the section states an exact in-code status rule that the changed function no longer implements directly. The new delegation is explicit and useful to document. The provider's actual classification rules remain unavailable and must not be asserted.
Model explanation: The function now delegates to `client.retry_provider.is_retryable(response)`, so the specific status codes are no longer directly checked in the function. The current text asserts specific status codes, which is no longer directly supported by the code. A bounded update referencing the retry provider is useful and safe.
Safe claims: ["The `can_retry` function now takes a `client` argument.", "The `can_retry` function returns the result of `client.retry_provider.is_retryable(response)`."]
Unsupported claims: ["The retry provider uses the same status codes (408, 429, 5xx) as the old function.", "The retry provider has any specific logic for retryable status codes."]

Proposed text:

```markdown
## Retry classification

Whether a response is retryable is determined by the retry provider.
```
Proposal review: The proposal delegates retryability to the provider and does not repeat the unsupported status-code list.

Checks:
- PASS: section decision matches frozen label
- PASS: evidence completeness matches frozen label
- PASS: missing information agrees with completeness
- PASS: safe claims supplied for UPDATE
- PASS: proposed text exists only for UPDATE
- PASS: section result contains the requested section exactly once
- PASS: application aggregation matches returned section decisions
- PASS: workflow state matches the frozen section label
- PASS: proposal review: safe claims are supported by supplied evidence
- PASS: proposal review: proposed facts are supported by safe_claims
- PASS: proposal review: no unsupported claim is asserted
- PASS: proposal review: frozen claim rubric is satisfied
- PASS: proposal review: missing information covers frozen evidence gaps

### H8: A connection wrapper changes to a manager whose implementation is absent

Result: **SEMANTIC_FAIL**
Expected decision/completeness: **UNCERTAIN / INSUFFICIENT**; actual: **UPDATE / COMPLETE**.
Expected missing information: ["session_manager.open implementation", "underlying transport and any additional behavior"]
Model-identified missing information: []

Available evidence:
- The wrapper now returns session_manager.open(host).

Intentionally unavailable evidence:
- The session manager implementation is not supplied.

Adjudication: UNCERTAIN is appropriate because the unavailable session manager may still open a direct TCP socket, so the existing transport claim is not demonstrably stale. A delegation-only replacement would not answer the user-facing transport question. The manager implementation and actual transport are needed to determine whether the current section remains accurate.
Model explanation: The function no longer creates a socket directly; it passes the host to a session_manager. The old text is factually incorrect.
Safe claims: ["The function signature now accepts a session_manager argument.", "The function returns the result of session_manager.open(host)."]
Unsupported claims: ["The type of session_manager.", "The internal implementation of session_manager.open(host)."]

Proposed text:

```markdown
## Open session

The wrapper delegates to `session_manager.open(host)` to establish a connection.
```
Proposal review: The direct delegation is supported, but 'to establish a connection' attributes behavior to the unavailable open method. The response also fails to recognize that the manager may still use a direct TCP socket, so the current documentation is not demonstrably stale.

Checks:
- FAIL: section decision matches frozen label
- FAIL: evidence completeness matches frozen label
- PASS: missing information agrees with completeness
- PASS: safe claims supplied for UPDATE
- PASS: proposed text exists only for UPDATE
- PASS: section result contains the requested section exactly once
- PASS: application aggregation matches returned section decisions
- FAIL: workflow state matches the frozen section label
- PASS: proposal review: safe claims are supported by supplied evidence
- FAIL: proposal review: proposed facts are supported by safe_claims
- FAIL: proposal review: no unsupported claim is asserted
- PASS: proposal review: frozen claim rubric is satisfied
- FAIL: proposal review: missing information covers frozen evidence gaps
Failed checks: section decision matches frozen label, evidence completeness matches frozen label, workflow state matches the frozen section label, proposal review: proposed facts are supported by safe_claims, proposal review: no unsupported claim is asserted, proposal review: missing information covers frozen evidence gaps

### H9: A fixed retention value changes to a deployment environment variable

Result: **PASS**
Expected decision/completeness: **UPDATE / PARTIAL**; actual: **UPDATE / PARTIAL**.
Expected missing information: ["RETENTION_DAYS runtime value", "behavior when RETENTION_DAYS is absent"]
Model-identified missing information: ["Whether RETENTION_DAYS has a fallback default value in the application or configuration when missing or invalid", "Whether the code handles KeyError or ValueError from os.environ['RETENTION_DAYS']"]

Available evidence:
- The new function reads and converts the RETENTION_DAYS environment variable.

Intentionally unavailable evidence:
- The deployment environment value and any runtime default policy are not supplied.

Adjudication: UPDATE is appropriate because the prior section gives a fixed 30-day default, while the new implementation reads RETENTION_DAYS. The environment-driven source is directly visible; the runtime value and behavior when the variable is unset are not.
Model explanation: The hardcoded default of 30 days is no longer accurate because the function now reads `RETENTION_DAYS` from the environment. The evidence supports replacing the specific 30-day claim with a statement about the environment variable source. A bounded note about a default cannot be added because the code shown raises an exception if the variable is missing or invalid; asserting a default value would be unsupported.
Safe claims: ["The function `retention_days` now reads an environment variable named RETENTION_DAYS", "The function returns the integer value of that environment variable"]
Unsupported claims: ["That a default retention of 30 days still applies", "That the function falls back to 30 days if the environment variable is not set or invalid", "That the environment variable is optional"]

Proposed text:

```markdown
## Retention days

Records are retained based on the `RETENTION_DAYS` environment variable.
```
Proposal review: The proposal states only that retention depends on RETENTION_DAYS; it does not assert a current value or fallback.

Checks:
- PASS: section decision matches frozen label
- PASS: evidence completeness matches frozen label
- PASS: missing information agrees with completeness
- PASS: safe claims supplied for UPDATE
- PASS: proposed text exists only for UPDATE
- PASS: section result contains the requested section exactly once
- PASS: application aggregation matches returned section decisions
- PASS: workflow state matches the frozen section label
- PASS: proposal review: safe claims are supported by supplied evidence
- PASS: proposal review: proposed facts are supported by safe_claims
- PASS: proposal review: no unsupported claim is asserted
- PASS: proposal review: frozen claim rubric is satisfied
- PASS: proposal review: missing information covers frozen evidence gaps

### H10: Protocol preference now depends on an unavailable runtime profile

Result: **SEMANTIC_FAIL**
Expected decision/completeness: **UNCERTAIN / INSUFFICIENT**; actual: **UPDATE / PARTIAL**.
Expected missing information: ["runtime_profile.alpn_protocols implementation", "the active runtime profile's protocol ordering and policy"]
Model-identified missing information: ["The exact return value and decision logic of `runtime_profile.alpn_protocols(supported_protocols)`. Whether it still prefers HTTP/2 when both are supported, or what other protocols it may support."]

Available evidence:
- The new function delegates protocol selection to runtime_profile.alpn_protocols(supported_protocols).

Intentionally unavailable evidence:
- The runtime profile implementation, active environment configuration, and resulting protocol preference are not supplied.

Adjudication: UNCERTAIN is appropriate because the documented protocol preference may remain true or may have changed under the unavailable runtime profile. A sentence naming the delegation would not answer the documented preference question. The provider policy and active protocol ordering are needed to determine whether the existing statement remains accurate.
Model explanation: The previous implementation logic was removed. The current text describes a specific literal check that no longer exists in the code. A bounded update is possible: we can preserve the original preference statement (which may still reflect the intended behavior) and add a note that the actual determination is delegated to `runtime_profile.alpn_protocols`. This avoids inventing facts about the delegated function while keeping the documentation accurate to the code change.
Safe claims: ["The `preferred_protocol` function now delegates to `runtime_profile.alpn_protocols(supported_protocols)`.", "The previous inline conditional logic for protocol preference was removed."]
Unsupported claims: ["That `runtime_profile.alpn_protocols` returns 'h2' when both 'h2' and 'http/1.1' are in the supported set.", "That the function still prefers HTTP/2 whenever both support it.", "That no other protocols are now considered."]

Proposed text:

```markdown
## Protocol preference

HTTP/2 is preferred whenever both the client and server support it.

Actual protocol preference is delegated to `runtime_profile.alpn_protocols(supported_protocols)`.
```
Proposal review: The response lists the old HTTP/2 preference as unsupported, then repeats it as current documentation. The delegated runtime profile could select a different ordering.

Checks:
- FAIL: section decision matches frozen label
- FAIL: evidence completeness matches frozen label
- PASS: missing information agrees with completeness
- PASS: safe claims supplied for UPDATE
- PASS: proposed text exists only for UPDATE
- PASS: section result contains the requested section exactly once
- PASS: application aggregation matches returned section decisions
- FAIL: workflow state matches the frozen section label
- PASS: proposal review: safe claims are supported by supplied evidence
- FAIL: proposal review: proposed facts are supported by safe_claims
- FAIL: proposal review: no unsupported claim is asserted
- FAIL: proposal review: frozen claim rubric is satisfied
- PASS: proposal review: missing information covers frozen evidence gaps
Failed checks: section decision matches frozen label, evidence completeness matches frozen label, workflow state matches the frozen section label, proposal review: proposed facts are supported by safe_claims, proposal review: no unsupported claim is asserted, proposal review: frozen claim rubric is satisfied

### H11: Sensitive-data encryption policy is delegated to an unavailable third-party provider

Result: **SEMANTIC_FAIL**
Expected decision/completeness: **UNCERTAIN / INSUFFICIENT**; actual: **UPDATE / COMPLETE**.
Expected missing information: ["crypto_provider.requires_encryption implementation", "the provider's encryption policy for sensitive records"]
Model-identified missing information: []

Available evidence:
- The changed wrapper now calls crypto_provider.requires_encryption(record).

Intentionally unavailable evidence:
- The third-party crypto provider implementation and configured policy are not supplied.

Adjudication: UNCERTAIN is appropriate because the provider may preserve or alter the sensitive-record rule, and its implementation is unavailable. Describing the internal delegation would not resolve the user-facing encryption guarantee. The provider policy is needed to know whether the current section remains accurate or to write a useful replacement.
Model explanation: The function `should_encrypt` no longer checks `record.get('sensitive', False)`; it delegates to `crypto_provider.requires_encryption(record)`. The current text still claims encryption is based on a 'sensitive' flag, which is no longer accurate. The proposed text updates the statement to reflect the new delegated behavior without inventing details about `crypto_provider`.
Safe claims: ["The function `should_encrypt` now delegates encryption requirement to `crypto_provider.requires_encryption(record)` instead of reading a 'sensitive' key from the record."]
Unsupported claims: ["The `crypto_provider.requires_encryption` method returns a boolean.", "The `crypto_provider` is a singleton or globally configured instance.", "The record format or fields passed to `crypto_provider.requires_encryption` are unchanged."]

Proposed text:

```markdown
## Encryption policy

Records marked sensitive are encrypted before storage, determined by the crypto provider's requirements.
```
Proposal review: The proposal preserves the sensitive-record encryption guarantee even though the provider policy is unavailable. The unsupported_claims list does not identify that very assertion.

Checks:
- FAIL: section decision matches frozen label
- FAIL: evidence completeness matches frozen label
- PASS: missing information agrees with completeness
- PASS: safe claims supplied for UPDATE
- PASS: proposed text exists only for UPDATE
- PASS: section result contains the requested section exactly once
- PASS: application aggregation matches returned section decisions
- FAIL: workflow state matches the frozen section label
- PASS: proposal review: safe claims are supported by supplied evidence
- FAIL: proposal review: proposed facts are supported by safe_claims
- FAIL: proposal review: no unsupported claim is asserted
- FAIL: proposal review: frozen claim rubric is satisfied
- FAIL: proposal review: missing information covers frozen evidence gaps
Failed checks: section decision matches frozen label, evidence completeness matches frozen label, workflow state matches the frozen section label, proposal review: proposed facts are supported by safe_claims, proposal review: no unsupported claim is asserted, proposal review: frozen claim rubric is satisfied, proposal review: missing information covers frozen evidence gaps

## Scorecard and exit decision

| Expected decision | Correct | Scored | Accuracy | Infrastructure errors |
|---|---:|---:|---:|---:|
| UPDATE | 5 | 5 | 100% | 0 |
| NO_CHANGE | 2 | 2 | 100% | 0 |
| UNCERTAIN | 0 | 4 | 0% | 0 |

Evidence-completeness accuracy: 7/11 (64%) among valid model outputs.
Proposal factual support: 11/17 proposals supported by their safe_claims and frozen rubric.
Unsupported-claim violations: 5.
Section-to-case aggregation: 11/11.
HITL checks: Scenario 5 PASS; Scenario 6 PASS.
Original behavior regressions vs accepted Phase 1 baseline: none.
Phase 1 decision: **Do not freeze the reasoning contract as calibrated; report the observed decision, completeness, claim-safety, and original-benchmark failures, then make any next change only as a separately scoped evaluation round.**

Limitations:
- The held-out set has 11 controlled cases and four genuine UNCERTAIN cases. This remains a small synthetic evaluation and does not establish a calibrated error rate.
- The evaluation uses one Sarvam model and one repository-shaped fixture set; it does not establish performance across projects, languages, dependency graphs, or runtime environments.
- Claim support is a documented manual review against the pre-call frozen claims and proposal rubrics.

## Recommended Phase 2 plan (not implemented)

1. **GitHub trigger:** add a least-privilege GitHub App/webhook that queues relevant pull-request or commit changes and deduplicates delivery IDs.
2. **Persistent online case state:** move cases, mappings, evidence assessments, model calls, and review events from local SQLite to a durable database with authenticated repository ownership.
3. **Review surface:** show changed symbols, mapped sections, evidence completeness, missing information, safe and unsupported claims, proposed edits, and explicit human approve/reject/modify actions.
4. **Approved documentation commit:** create a narrowly scoped branch or pull request only after approval, with conflict checks and an audit link to the approved proposal.
5. **Approved-only indexing:** ingest only from approved documentation commits and record their source revisions; keep pending or rejected text out of the index.
6. **Chat:** answer from the approved index with citations to documentation revisions and preserve the review trail for corrections.
