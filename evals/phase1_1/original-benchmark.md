# HTTPX Phase 1 Live Evaluation

Generated: 2026-10-02T22:59:39.012840+00:00
Pinned base: `b5addb64f0161ff6bfe94c124ef76f6a1fba5254`

## Original run errors

No prior report with recorded errors was provided.

## New scenario results

### Scenario 1: Default timeout changes from five to eight seconds

Result: **SEMANTIC_FAIL**  
Expected: **UPDATE**  
Actual: **UPDATE**  
Case: `9c4f9ba4-d8f0-4410-aa80-1cb1464734eb`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::__intro__`: **UPDATE** — The code diff changes DEFAULT_TIMEOUT_CONFIG from Timeout(timeout=5.0) to Timeout(timeout=8.0), directly contradicting the documentation's claim of a 5-second default.

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of
  network inactivity.
  ```
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`: **NO_CHANGE** — This section demonstrates how to set a timeout on a client instance using httpx.Client(timeout=...). It does not state or imply the specific default value of the library's built-in default timeout.
- `docs/quickstart.md::timeouts`: **NO_CHANGE** — This section discusses that HTTPX defaults to including reasonable timeouts and mentions the default is 'five seconds', but this is a general statement about the concept of timeouts. The specific value of 5.0 seconds is not the only thing changed; the code change to 8.0 seconds is a specific implementation detail. However, since this section explicitly states 'The default timeout for network inactivity is five seconds', it is also factually incorrect based on the new code. Wait, re-evaluating: the section explicitly states 'five seconds', which is now incorrect. The code change from 5.0 to 8.0 makes this statement false. Therefore, this section should be updated as well to maintain consistency, or at least the specific claim about 'five seconds' should be corrected. However, the section is about general timeout behavior and how to modify it, not specifically about the default value. The text 'The default timeout for network inactivity is five seconds' is a direct factual claim that is now wrong. I should update this as well to 'eight seconds' or remove the specific number. But the instruction says 'make the smallest justified edit'. Changing 'five seconds' to 'eight seconds' is the smallest edit. But wait, the user asked to compare old and new code and the Git diff with the supplied current text. The current text of docs/quickstart.md::timeouts explicitly says 'five seconds'. The code now has 8.0. So this is also a direct contradiction. I need to update this too.

Sarvam call diagnostics:
- Call 1: operation=impact, model=sarvam-105b, prompt=impact.v3, schema=impact_analysis, candidates=docs/advanced/timeouts.md::__intro__,docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client,docs/quickstart.md::timeouts, max_tokens=8192, retry=0, finish=stop, tokens=1797/865/2662, validation=passed, latency_ms=4827.1, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_b610ab4a-f50d-4917-9a54-130fd9470137

### Scenario 2: Internal Timeout.as_dict refactor preserves behavior

Result: **PASS**  
Expected: **NO_CHANGE**  
Actual: **NO_CHANGE**  
Case: `e6dc6892-31d1-43a3-ac2a-8f27b29cd649`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::fine-tuning-the-configuration`

Sarvam section decisions:
- `docs/advanced/timeouts.md::fine-tuning-the-configuration`: **NO_CHANGE** — The code change is a refactor of as_dict() to use a zip-based dictionary construction. This does not change any documented timeout behavior, parameter names, or exception types. The documentation section does not reference as_dict().

  Missing information:
  - The documentation does not mention as_dict(), so there is no direct semantic link to update. The behavior described is established by the class structure and __init__ parameters, which are unchanged.

Sarvam call diagnostics:
- Call 1: operation=impact, model=sarvam-105b, prompt=impact.v3, schema=impact_analysis, candidates=docs/advanced/timeouts.md::fine-tuning-the-configuration, max_tokens=8192, retry=0, finish=length, tokens=3798/8192/11990, validation=failed, latency_ms=43197.17, error=MODEL_CONTRACT_ERROR
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_dd81cbaa-32ef-4066-804f-39f15c1ed86d
- Call 2: operation=impact, model=sarvam-105b, prompt=impact.v3, schema=impact_analysis, candidates=docs/advanced/timeouts.md::fine-tuning-the-configuration, max_tokens=8192, retry=1, finish=stop, tokens=3888/502/4390, validation=passed, latency_ms=2969.49, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_4a6c388f-2c3c-4af7-8b71-30cd3be82b3e

### Scenario 3: Timeout.is_disabled public property added

Result: **PASS**  
Expected: **UPDATE**  
Actual: **UPDATE**  
Case: `7885070f-c15f-40b0-88ea-6b5239f795b2`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::setting-and-disabling-timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::setting-and-disabling-timeouts`: **UPDATE** — The new `is_disabled` property is added to the `Timeout` class. The documentation section describes how to disable timeouts but does not mention this new property. The proposed text adds a paragraph and code examples showing how to use `is_disabled` to check if a `Timeout` instance is disabled, which is a natural extension of the existing content.

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
  
  You can also check if a `Timeout` instance is disabled by using the `is_disabled` property:
  
  ```python
  from httpx import Timeout
  
  # No timeouts.
  assert Timeout(None).is_disabled
  
  # 5s timeout on all operations.
  assert not Timeout(5.0).is_disabled
  
  # 5s timeout on connect, no other timeouts.
  assert not Timeout(None, connect=5.0).is_disabled
  ```
  ```

Sarvam call diagnostics:
- Call 1: operation=impact, model=sarvam-105b, prompt=impact.v3, schema=impact_analysis, candidates=docs/advanced/timeouts.md::setting-and-disabling-timeouts, max_tokens=8192, retry=0, finish=length, tokens=3330/8192/11522, validation=failed, latency_ms=44728.16, error=MODEL_CONTRACT_ERROR
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_510a3c91-9bce-45e9-b827-4d83c56eaee8
- Call 2: operation=impact, model=sarvam-105b, prompt=impact.v3, schema=impact_analysis, candidates=docs/advanced/timeouts.md::setting-and-disabling-timeouts, max_tokens=8192, retry=1, finish=stop, tokens=3421/661/4082, validation=passed, latency_ms=3610.69, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_683d89fa-60e4-451e-8da9-72b381182bbe

### Scenario 4: Default timeout comes from an unavailable external runtime policy

Result: **SEMANTIC_FAIL**  
Expected: **UNCERTAIN**  
Actual: **UPDATE**  
Case: `ebf9b31f-54a5-4ec2-a761-7bce787716b6`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::__intro__`: **UPDATE** — The code change replaces `Timeout(timeout=5.0)` with `Timeout(timeout=timeout_seconds())`, indicating the default timeout is no longer a hardcoded constant. The documentation must be updated to reflect this, while preserving the 5-second reference as the prior default value. The external function's behavior is unknown, so we note the policy-driven nature of the change without fabricating a specific value.

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after a default timeout
  period of 5 seconds of network inactivity. This default is now determined by
  the `timeout_seconds()` runtime policy function.
  ```
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`: **NO_CHANGE** — This section describes how to set a default timeout on a client instance via the `timeout` parameter. It does not describe the library-level default configuration value. The change to `DEFAULT_TIMEOUT_CONFIG` does not affect the API or behavior of setting a timeout on a client, so no documentation update is needed.
- `docs/quickstart.md::timeouts`: **UPDATE** — The quickstart section explicitly states 'The default timeout for network inactivity is five seconds.' The code change replaces this hardcoded 5.0 with `timeout_seconds()`, so the documentation must be updated to indicate the default is now determined by runtime policy, while preserving the five-second reference. The rest of the section is unaffected.

  Proposed text:

  ```markdown
  ## Timeouts
  
  HTTPX defaults to including reasonable timeouts for all network operations,
  meaning that if a connection is not properly established then it should always
  raise an error rather than hanging indefinitely.
  
  The default timeout for network inactivity is five seconds, determined by the
  `timeout_seconds()` runtime policy function. You can modify the value to be more
  or less strict:
  
  ```pycon
  >>> httpx.get('https://github.com/', timeout=0.001)
  ```
  
  You can also disable the timeout behavior completely...
  
  ```pycon
  >>> httpx.get('https://github.com/', timeout=None)
  ```
  
  For advanced timeout management, see [Timeout fine-tuning](advanced/timeouts.md#fine-tuning-the-configuration).
  ```

Sarvam call diagnostics:
- Call 1: operation=impact, model=sarvam-105b, prompt=impact.v3, schema=impact_analysis, candidates=docs/advanced/timeouts.md::__intro__,docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client,docs/quickstart.md::timeouts, max_tokens=8192, retry=0, finish=stop, tokens=1844/894/2738, validation=passed, latency_ms=4777.32, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_3881344a-a254-4d7f-abb9-244ad3c189de

### Scenario 5: Reject a proposal, require an observable scope clarification, then accept V2

Result: **SEMANTIC_FAIL**  
Expected: **UPDATE**  
Actual: **UPDATE**  
Case: `9c4f9ba4-d8f0-4410-aa80-1cb1464734eb`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::__intro__`: **UPDATE** — The reviewer rejected the previous proposal because it did not clarify that the timeout is specifically for network inactivity and not an overall request deadline. The revised text adds this clarification while preserving the corrected 8-second value and the accurate current documentation.

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of network inactivity. This timeout applies to the period of network inactivity and does not represent an overall deadline for the complete HTTP request.
  ```

Sarvam call diagnostics:
- Call 1: operation=revision, model=sarvam-105b, prompt=revision.v2, schema=proposal_revision, candidates=docs/advanced/timeouts.md::__intro__, max_tokens=4096, retry=0, finish=stop, tokens=1132/154/1286, validation=passed, latency_ms=1044.16, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_bc3345df-823d-45a3-a2df-132731d72fd0

Human actions: `[{"action": "REJECT", "version_id": "93c2ed51-267a-45d6-9b6b-b3dc465c7ba2", "reason": "The value change is correct, but explicitly clarify that this is a network-inactivity timeout and not an overall deadline for the complete HTTP request."}, {"action": "ACCEPT", "version_id": "7f912cd3-cce9-4875-9e8e-4b35769513e1", "reason": null}]`

Revision checks:
- V1 preserved: `True`
- rejection event and exact reason preserved: `True`
- V2 differs from V1: `True`
- requested feedback appears in V2: `False`
- only rejected proposal gained a version: `True`
- V2 explicitly accepted: `True`

Reviewer feedback: The value change is correct, but explicitly clarify that this is a network-inactivity timeout and not an overall deadline for the complete HTTP request.

Rejected proposal versions:
- V1 (sarvam, sha256 `daf4b4362e73f3e8e5764e4c25bd3d090e743a48ea5067878b90f5583e488259`):

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of
  network inactivity.
  ```
- V2 (sarvam, sha256 `ad0dba04b4263b128cb484001da6fe4c4bc5cf7f29f76c3bc72f8b780fe2016c`):

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of network inactivity. This timeout applies to the period of network inactivity and does not represent an overall deadline for the complete HTTP request.
  ```

### Scenario 6: Human-modify a persisted UPDATE, accept it, and apply it without a Sarvam rewrite

Result: **PASS**  
Expected: **UPDATE**  
Actual: **UPDATE**  
Case: `04eae1f2-9868-43a6-a961-70f7bc042eeb`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`

Sarvam section decisions:
- `docs/advanced/timeouts.md::__intro__`: **UPDATE** — 

  Proposed text:

  ```markdown
  The default timeout is 8 seconds of network inactivity.
  
  This setting does not impose an overall deadline for the complete HTTP request.
  ```

Sarvam call diagnostics:

Human actions: `[{"action": "MODIFY", "version_id": "b308df6e-f533-4faa-a811-557b3190c1b6", "content": "The default timeout is 8 seconds of network inactivity.\n\nThis setting does not impose an overall deadline for the complete HTTP request.\n"}, {"action": "ACCEPT", "version_id": "b308df6e-f533-4faa-a811-557b3190c1b6", "content": null}]`

Revision checks:
- human-authored version stored exactly: `True`
- no Sarvam rewrite during review: `True`
- human version explicitly accepted: `True`

Apply checks:
- apply command succeeded: `True`
- exact human text appears in documentation: `True`
- applied version is the human version: `True`
- section hash recorded: `True`
- file hash recorded: `True`
- no Sarvam calls for human edit: `True`

Final applied text:

```markdown
The default timeout is 8 seconds of network inactivity.

This setting does not impose an overall deadline for the complete HTTP request.
```

## Summary

- API_ERROR: 0
- MODEL_CONTRACT_ERROR: 0
- PASS: 3
- SEMANTIC_FAIL: 3
- SYSTEM_ERROR: 0
