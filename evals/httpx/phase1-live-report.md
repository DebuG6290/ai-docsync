# HTTPX Phase 1 Live Evaluation

Generated: 2026-10-02T22:42:24.703820+00:00
Pinned base: `b5addb64f0161ff6bfe94c124ef76f6a1fba5254`

## Original run errors

### Scenario 2: ERROR

Observed: `ModelError: Sarvam response omitted, duplicated, or introduced candidate section IDs`

Sarvam's parsed impact output failed exact candidate-ID set equality. The old code reported the combined failure but did not retain which IDs were missing, duplicated, or unknown.

### Scenario 3: ERROR

Observed: `ModelError: Sarvam response content was not text`

The adapter assumed choices[0].message.content must already be a string and rejected the response. The original run stored no content type, finish reason, or message metadata, so the exact provider shape cannot be reconstructed from that report.

### Scenario 4: ERROR

Observed: `ModelError: Sarvam returned malformed or schema-invalid impact_analysis: 1 validation error for ImpactResponse
  Invalid JSON: EOF while parsing a string at line 1 column 2884 [type=json_invalid, input_value='{"decision":"NO_CHANGE",...\n>>> httpx.get(\'https', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/json_invalid`

Pydantic received an incomplete JSON string and reported EOF. The old adapter did not inspect finish_reason or token usage, so the report cannot establish whether Sarvam hit its output limit or returned malformed JSON for another reason.

### Scenario 6: ERROR

Observed: `ModelError: Sarvam response content was not text`

The adapter assumed choices[0].message.content must already be a string and rejected the response. The original run stored no content type, finish reason, or message metadata, so the exact provider shape cannot be reconstructed from that report.

## Legacy request shape replays

### Scenario 3: REPRODUCED_OLD_NON_TEXT_SHAPE

Request: model=sarvam-105b, legacy_max_tokens=12000, response_model=sarvam-105b, response_id=None
Response: envelope=dict/chat.completion, choices=1, finish=length, message=dict, content=NoneType, content_length=None, input/output/total tokens=3169/12000/15169
reasoning_field=True (nonempty=True), tool_calls_field=True (nonempty=False)

Replaying the original Scenario 3 input with the old request contract reproduced the non-text failure: finish_reason=length, content=null, and reasoning_content was nonempty after the 12,000 completion-token budget was exhausted.

### Scenario 6: OLD_NON_TEXT_SHAPE_NOT_REPRODUCED

Request: model=sarvam-105b, legacy_max_tokens=12000, response_model=sarvam-105b, response_id=None
Response: envelope=dict/chat.completion, choices=1, finish=stop, message=dict, content=str, content_length=3648, input/output/total tokens=1636/10382/12018
reasoning_field=True (nonempty=True), tool_calls_field=True (nonempty=False)

The replay of the old Scenario 6 input returned text and finish_reason=stop, so the old non-text shape did not reproduce. The original response had no structural diagnostics and its exact shape cannot be recovered.

### Scenario 4: FRESH_LEGACY_REPLAY_RETURNED_TEXT

Request: model=sarvam-105b, legacy_max_tokens=12000, response_model=sarvam-105b, response_id=None
Response: envelope=dict/chat.completion, choices=1, finish=stop, message=dict, content=str, content_length=4131, input/output/total tokens=1683/11920/13603
reasoning_field=True (nonempty=True), tool_calls_field=True (nonempty=False)

A fresh replay did not reproduce the original EOF response. The original report did not store its finish_reason or content shape; this replay therefore cannot establish whether that original output was truncated.

## New scenario results

### Scenario 1: Default timeout changes from five to eight seconds

Result: **PASS**  
Expected: **UPDATE**  
Actual: **UPDATE**  
Case: `203ecdff-3909-4994-8dc5-a091c4e57601`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::__intro__`: **UPDATE** — The code change changes DEFAULT_TIMEOUT_CONFIG from 5.0 to 8.0. The __intro__ section explicitly states the default timeout is 5 seconds, which is now incorrect.

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of
  network inactivity.
  ```
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`: **UPDATE** — The example comment in the code block shows 'Use a default 5s timeout everywhere.' which no longer matches the new default of 8s. The comment should be updated to 8s to reflect the new default behavior.

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
- `docs/quickstart.md::timeouts`: **UPDATE** — The quickstart section explicitly states 'The default timeout for network inactivity is five seconds.' This must be updated to 'eight seconds' to match the new DEFAULT_TIMEOUT_CONFIG value of 8.0.

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

Sarvam call diagnostics:
- Call 1: operation=impact, model=sarvam-105b, prompt=impact.v2, schema=impact_analysis, candidates=docs/advanced/timeouts.md::__intro__,docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client,docs/quickstart.md::timeouts, max_tokens=8192, retry=0, finish=stop, tokens=1658/719/2377, validation=passed, latency_ms=3979.69, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_db753c83-8806-48d7-b65f-f89949171d82

### Scenario 2: Internal Timeout.as_dict refactor preserves behavior

Result: **PASS**  
Expected: **NO_CHANGE**  
Actual: **NO_CHANGE**  
Case: `b00c7498-8cae-44d2-bef1-0014ea29b112`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::fine-tuning-the-configuration`

Sarvam section decisions:
- `docs/advanced/timeouts.md::fine-tuning-the-configuration`: **NO_CHANGE** — The `as_dict()` implementation change is a structural refactoring (using `zip` instead of a literal dict) that preserves the exact same key-value pairs and return type (`dict[str, float | None]`). The documentation already correctly describes the four timeout types and their configuration. The refactoring does not alter behavior, add features, or fix bugs that would require documentation updates.

Sarvam call diagnostics:
- Call 1: operation=impact, model=sarvam-105b, prompt=impact.v2, schema=impact_analysis, candidates=docs/advanced/timeouts.md::fine-tuning-the-configuration, max_tokens=8192, retry=0, finish=stop, tokens=3659/561/4220, validation=passed, latency_ms=3243.97, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_93160f42-0c8e-40f5-ad7a-3286b74d5ba3

### Scenario 3: Timeout.is_disabled public property added

Result: **PASS**  
Expected: **UPDATE**  
Actual: **UPDATE**  
Case: `6862a2be-b1fe-4315-b242-317276005e1a`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::setting-and-disabling-timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::setting-and-disabling-timeouts`: **UPDATE** — The diff adds a new `Timeout.is_disabled` property to `httpx/_config.py` that returns `True` when all timeout values (connect, read, write, pool) are `None`. The current section covers setting and disabling timeouts but does not mention this property. Adding a small usage example preserves the existing style and correctly documents the new API without inferring undocumented behavior.

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
  
  You can also check if a `Timeout` object is fully disabled using the `is_disabled` property:
  
  ```python
  timeout = Timeout(None, connect=5.0)
  
  if timeout.is_disabled:
      print('No timeouts are set.')
  ```
  ```

Sarvam call diagnostics:
- Call 1: operation=impact, model=sarvam-105b, prompt=impact.v2, schema=impact_analysis, candidates=docs/advanced/timeouts.md::setting-and-disabling-timeouts, max_tokens=8192, retry=0, finish=stop, tokens=3191/487/3678, validation=passed, latency_ms=3050.48, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_ee551230-8b9a-4444-89bd-e93694900c11

### Scenario 4: Default timeout comes from an unavailable external runtime policy

Result: **SEMANTIC_FAIL**  
Expected: **UNCERTAIN**  
Actual: **UPDATE**  
Case: `ee967d4e-e4cf-41d6-9e2e-03cb9ba03720`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::__intro__`: **UPDATE** — The old text says 5 seconds. The new code uses `timeout_seconds()`, so the exact value is no longer hard-coded in this file. We must remove the hard-coded 5 seconds and cite the runtime policy instead. The rest of the sentence is unchanged.

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after `timeout_seconds()`
  of network inactivity.
  ```
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`: **NO_CHANGE** — This section describes how to set a client-level timeout explicitly. It does not mention the global default value, so the change from 5.0 to `timeout_seconds()` is not relevant here.
- `docs/quickstart.md::timeouts`: **UPDATE** — The old text states the default is 'five seconds'. The new code replaces the hard-coded 5.0 with `timeout_seconds()`, so the default is now runtime-configurable. We replace 'five seconds' with 'determined by `timeout_seconds()`' to remain accurate without inventing a new fixed value.

  Proposed text:

  ```markdown
  ## Timeouts
  
  HTTPX defaults to including reasonable timeouts for all network operations,
  meaning that if a connection is not properly established then it should always
  raise an error rather than hanging indefinitely.
  
  The default timeout for network inactivity is determined by `timeout_seconds()`.
  You can modify the value to be more or less strict:
  
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
- Call 1: operation=impact, model=sarvam-105b, prompt=impact.v2, schema=impact_analysis, candidates=docs/advanced/timeouts.md::__intro__,docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client,docs/quickstart.md::timeouts, max_tokens=8192, retry=0, finish=stop, tokens=1705/694/2399, validation=passed, latency_ms=4507.58, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_bc461cef-3acd-47d8-9a82-67456f6a2a3e

### Scenario 5: Reject a proposal, require an observable scope clarification, then accept V2

Result: **PASS**  
Expected: **UPDATE**  
Actual: **UPDATE**  
Case: `203ecdff-3909-4994-8dc5-a091c4e57601`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::__intro__`: **UPDATE** — The reviewer rejected the previous proposal because it did not explicitly clarify that the timeout is for network inactivity and not an overall deadline. The revised text adds this clarification while preserving the accurate current documentation (the 8 second value) and satisfying the review reason using only supplied code evidence (the DEFAULT_TIMEOUT_CONFIG change from 5.0 to 8.0).

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of network inactivity, not an overall deadline for the complete HTTP request.
  ```

Sarvam call diagnostics:
- Call 1: operation=revision, model=sarvam-105b, prompt=revision.v2, schema=proposal_revision, candidates=docs/advanced/timeouts.md::__intro__, max_tokens=4096, retry=0, finish=stop, tokens=1143/180/1323, validation=passed, latency_ms=1200.59, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_44806d3d-a733-4980-b252-dfacc7c3e86c

Human actions: `[{"action": "REJECT", "version_id": "9d2a21f2-5849-4da3-ab01-d2e5c80eb2c4", "reason": "The value change is correct, but explicitly clarify that this is a network-inactivity timeout and not an overall deadline for the complete HTTP request."}, {"action": "ACCEPT", "version_id": "b30feb09-66ff-4f06-ac37-dec0d6131ae7", "reason": null}]`

Revision checks:
- V1 preserved: `True`
- rejection event and exact reason preserved: `True`
- V2 differs from V1: `True`
- requested feedback appears in V2: `True`
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
- V2 (sarvam, sha256 `f4ca47df963f22f2750c28fa0ce03ae39992ce63ac1db858934fbcfc8e44da0c`):

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of network inactivity, not an overall deadline for the complete HTTP request.
  ```

### Scenario 6: Human-modify a persisted UPDATE, accept it, and apply it without a Sarvam rewrite

Result: **PASS**  
Expected: **UPDATE**  
Actual: **UPDATE**  
Case: `109e0a2c-d4cb-408a-8cfd-1048f5425459`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::__intro__`: **UPDATE** — 

  Proposed text:

  ```markdown
  The default timeout is 8 seconds of network inactivity.
  
  This setting does not impose an overall deadline for the complete HTTP request.
  ```

Sarvam call diagnostics:

Human actions: `[{"action": "MODIFY", "version_id": "accf6276-bdd2-49f1-af0b-a2845086de37", "content": "The default timeout is 8 seconds of network inactivity.\n\nThis setting does not impose an overall deadline for the complete HTTP request.\n"}, {"action": "ACCEPT", "version_id": "accf6276-bdd2-49f1-af0b-a2845086de37", "content": null}]`

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
- PASS: 5
- SEMANTIC_FAIL: 1
- SYSTEM_ERROR: 0
