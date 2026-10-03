# HTTPX Phase 1 Live Evaluation

Generated: 2026-10-02T23:38:14.505691+00:00
Pinned base: `b5addb64f0161ff6bfe94c124ef76f6a1fba5254`

## Original run errors

No prior report with recorded errors was provided.

## New scenario results

| Scenario | Previous Phase 1.1 result | New result | Regressed vs prior pass? | Accepted baseline |
|---:|---|---|---|---|
| 1 | SEMANTIC_FAIL | PASS | No | PASS |
| 2 | PASS | PASS | No | PASS |
| 3 | PASS | PASS | No | PASS |
| 4 | SEMANTIC_FAIL | SEMANTIC_FAIL | No | SEMANTIC_FAIL |
| 5 | SEMANTIC_FAIL | PASS | No | PASS |
| 6 | PASS | PASS | No | PASS |

### Scenario 1: Default timeout changes from five to eight seconds

Result: **PASS**  
Expected: **UPDATE**  
Actual: **UPDATE**  
Case: `1943d8a1-3fbc-49c2-9a84-444cae4e320a`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::__intro__`: **UPDATE** — The old text states the default is 5 seconds. The code changed the default to 8.0. This is a direct, factual update with no unsupported claims.
  Evidence completeness: **COMPLETE**; safe claims: ["DEFAULT_TIMEOUT_CONFIG is set to Timeout(timeout=8.0) in httpx/_config.py."]; unsupported claims: []
  Code evidence:
  - httpx/_config.py::DEFAULT_TIMEOUT_CONFIG: new_code = Timeout(timeout=8.0)

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of
  network inactivity.
  ```
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`: **UPDATE** — The example comment for the default client now reflects the new default of 8 seconds. This is the smallest useful edit to keep the example accurate.
  Evidence completeness: **COMPLETE**; safe claims: ["DEFAULT_TIMEOUT_CONFIG is set to Timeout(timeout=8.0) in httpx/_config.py."]; unsupported claims: []
  Code evidence:
  - httpx/_config.py::DEFAULT_TIMEOUT_CONFIG: new_code = Timeout(timeout=8.0)

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
- `docs/quickstart.md::timeouts`: **UPDATE** — The old text states the default is five seconds. The code changed the default to 8.0. This is a direct, factual update with no unsupported claims.
  Evidence completeness: **COMPLETE**; safe claims: ["DEFAULT_TIMEOUT_CONFIG is set to Timeout(timeout=8.0) in httpx/_config.py."]; unsupported claims: []
  Code evidence:
  - httpx/_config.md::DEFAULT_TIMEOUT_CONFIG: new_code = Timeout(timeout=8.0)

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

Sarvam call diagnostics:
- Call 1: operation=impact, model=sarvam-105b, prompt=impact.v4, schema=impact_analysis, candidates=docs/advanced/timeouts.md::__intro__,docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client,docs/quickstart.md::timeouts, max_tokens=8192, retry=0, finish=stop, tokens=1897/895/2792, validation=passed, latency_ms=5720.09, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_933533aa-cfd9-41eb-8bfb-1d53c56e1d2e

### Scenario 2: Internal Timeout.as_dict refactor preserves behavior

Result: **PASS**  
Expected: **NO_CHANGE**  
Actual: **NO_CHANGE**  
Case: `2a03d863-a0d8-4463-be19-d6f1b54235d4`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::fine-tuning-the-configuration`

Sarvam section decisions:
- `docs/advanced/timeouts.md::fine-tuning-the-configuration`: **NO_CHANGE** — The code change only refactors the implementation of `Timeout.as_dict()` to use a dictionary comprehension instead of a literal dictionary. This does not alter the behavior, return type, or semantics of the method. The documentation describes the conceptual timeout types and how to configure them, which remains unchanged. No useful replacement is needed.
  Evidence completeness: **COMPLETE**; safe claims: ["The `as_dict` method returns a dictionary mapping 'connect', 'read', 'write', and 'pool' to their respective timeout values.", "The method signature is `def as_dict(self) -> dict[str, float | None]`."]; unsupported claims: []
  Code evidence:
  - diff --git a/httpx/_config.py b/httpx/_config.py
index 467a6c9..88dd6ae 100644
--- a/httpx/_config.py
+++ b/httpx/_config.py
@@ -128,16 +128,13 @@ class Timeout:
             self.read = timeout if isinstance(read, UnsetType) else read
             self.write = timeout if isinstance(write, UnsetType) else write
             self.pool = timeout if isinstance(pool, UnsetType) else pool
 
     def as_dict(self) -> dict[str, float | None]:
-        return {
-            "connect": self.connect,
-            "read": self.read,
-            "write": self.write,
-            "pool": self.pool,
-        }
+        names = ("connect", "read", "write", "pool")
+        values = (self.connect, self.read, self.write, self.pool)
+        return {name: value for name, value in zip(names, values)}

     def __eq__(self, other: typing.Any) -> bool:
         return (
             isinstance(other, self.__class__)
             and self.connect == other.connect

Checks:
- PASS: returned exactly the mapped section IDs
- PASS: case workflow state matches frozen expected aggregation
- PASS: application workflow state matches section decisions
- PASS: section decision correct: docs/advanced/timeouts.md::fine-tuning-the-configuration
- PASS: evidence completeness correct: docs/advanced/timeouts.md::fine-tuning-the-configuration
- PASS: proposals exist exactly for UPDATE sections

Sarvam call diagnostics:
- Call 1: operation=impact, model=sarvam-105b, prompt=impact.v4, schema=impact_analysis, candidates=docs/advanced/timeouts.md::fine-tuning-the-configuration, max_tokens=8192, retry=0, finish=stop, tokens=3898/523/4421, validation=passed, latency_ms=3038.16, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_b17ad785-5acf-4d1f-944a-2757faca5940

### Scenario 3: Timeout.is_disabled public property added

Result: **PASS**  
Expected: **UPDATE**  
Actual: **UPDATE**  
Case: `f0051fc8-973a-4415-bc9a-4c290b0a6f4b`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::setting-and-disabling-timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::setting-and-disabling-timeouts`: **UPDATE** — The code adds `Timeout.is_disabled` which returns `True` when all timeout values are `None`, matching the documented behavior of `timeout=None`. The current text does not mention this property, so it should be updated to describe it. The evidence is COMPLETE because the new property's implementation is fully visible in the code.
  Evidence completeness: **COMPLETE**; safe claims: ["The `is_disabled` property returns `True` when all timeout values are `None`", "The `is_disabled` property is a read-only property on `Timeout` instances", "The `is_disabled` property uses `as_dict()` to check all timeout values"]; unsupported claims: ["The `is_disabled` property is used in the public API for any specific purpose", "The `is_disabled` property affects runtime behavior beyond its return value", "The `is_disabled` property is documented in any other section"]
  Code evidence:
  - class Timeout:
    @property
    def is_disabled(self) -> bool:
        return all(value is None for value in self.as_dict().values())

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

Checks:
- PASS: returned exactly the mapped section IDs
- PASS: case workflow state matches frozen expected aggregation
- PASS: application workflow state matches section decisions
- PASS: section decision correct: docs/advanced/timeouts.md::setting-and-disabling-timeouts
- PASS: evidence completeness correct: docs/advanced/timeouts.md::setting-and-disabling-timeouts
- PASS: proposals exist exactly for UPDATE sections
- PASS: proposal documents is_disabled

Sarvam call diagnostics:
- Call 1: operation=impact, model=sarvam-105b, prompt=impact.v4, schema=impact_analysis, candidates=docs/advanced/timeouts.md::setting-and-disabling-timeouts, max_tokens=8192, retry=0, finish=stop, tokens=3430/714/4144, validation=passed, latency_ms=4514.66, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_449daa0b-a42f-4a32-9be0-a2449e10c35a

### Scenario 4: Default timeout comes from an unavailable external runtime policy

Result: **SEMANTIC_FAIL**  
Expected: **UPDATE**  
Actual: **UPDATE**  
Case: `9ae0023e-e224-4741-b4e1-eb9ed26a6635`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::__intro__`: **UPDATE** — The old code hardcoded 5.0; the new code calls timeout_seconds(). The text should reflect the source of the default value without inventing a specific numeric value. The `timeout_seconds()` call is directly visible in the code diff.
  Evidence completeness: **COMPLETE**; safe claims: ["The default timeout value is now obtained by calling timeout_seconds()", "timeout_seconds() is imported from external_runtime_policy"]; unsupported claims: ["The numeric value returned by timeout_seconds() is 5 seconds", "timeout_seconds() is a function in the httpx package"]
  Code evidence:
  - new_code: DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=timeout_seconds())
  - diff: +from external_runtime_policy import timeout_seconds

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after `timeout_seconds()` seconds of
  network inactivity.
  ```
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`: **UPDATE** — The code change does not affect the client-level timeout API; the default for client() without an explicit timeout now comes from the updated DEFAULT_TIMEOUT_CONFIG. The examples remain valid, but the comment on the first example should be updated to avoid implying a fixed 5s default. The smallest useful edit is to change the comment.
  Evidence completeness: **COMPLETE**; safe claims: ["The default timeout for client() is now determined by the updated DEFAULT_TIMEOUT_CONFIG", "The client constructor still accepts timeout=10.0 and timeout=None"]; unsupported claims: ["The default timeout is 5 seconds", "The default timeout is configurable at runtime via external_runtime_policy"]
  Code evidence:
  - new_code: DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=timeout_seconds())

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
- `docs/quickstart.md::timeouts`: **UPDATE** — The old text states 'The default timeout for network inactivity is five seconds.' The new code uses timeout_seconds(). We should update the text to say the default is timeout_seconds() without inventing a numeric value. The rest of the section is unchanged.
  Evidence completeness: **COMPLETE**; safe claims: ["The default timeout value is now obtained by calling timeout_seconds()", "timeout_seconds() is imported from external_runtime_policy"]; unsupported claims: ["The numeric value returned by timeout_seconds() is 5 seconds", "timeout_seconds() is a function in the httpx package"]
  Code evidence:
  - new_code: DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=timeout_seconds())
  - diff: +from external_runtime_policy import timeout_seconds

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

Failed checks: evidence completeness correct: docs/advanced/timeouts.md::__intro__, evidence completeness correct: docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client, evidence completeness correct: docs/quickstart.md::timeouts

Sarvam call diagnostics:
- Call 1: operation=impact, model=sarvam-105b, prompt=impact.v4, schema=impact_analysis, candidates=docs/advanced/timeouts.md::__intro__,docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client,docs/quickstart.md::timeouts, max_tokens=8192, retry=0, finish=stop, tokens=1944/1059/3003, validation=passed, latency_ms=5634.96, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_4cd94761-30fd-4d69-9cec-6039fa8cbebe

### Scenario 5: Reject a proposal, require an observable scope clarification, then accept V2

Result: **PASS**  
Expected: **UPDATE**  
Actual: **UPDATE**  
Case: `1943d8a1-3fbc-49c2-9a84-444cae4e320a`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::__intro__`: **UPDATE** — The reviewer rejected the proposal because it did not explicitly clarify that the timeout is for network inactivity, not an overall deadline for the complete HTTP request. The revised text adds this clarification while keeping the factual update from 5 to 8 seconds.
  Evidence completeness: **n/a**; safe claims: []; unsupported claims: []

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of network inactivity. This timeout applies to periods when no data is being transmitted, not to the total duration of the request.
  ```

Sarvam call diagnostics:
- Call 1: operation=revision, model=sarvam-105b, prompt=revision.v3, schema=proposal_revision, candidates=docs/advanced/timeouts.md::__intro__, max_tokens=4096, retry=0, finish=stop, tokens=1377/235/1612, validation=passed, latency_ms=1419.46, error=None
  response: type=dict, choices=1, message=dict, content=str, reasoning_present=True (nonempty=False), tool_calls_present=True (nonempty=False), request_model=sarvam-105b, response_model=sarvam-105b, response_id=20261002_bf2a8aa4-843b-4533-9028-d6615b959da9

Human actions: `[{"action": "REJECT", "version_id": "92787948-8c2e-4f93-b877-c6762b9cd20e", "reason": "The value change is correct, but explicitly clarify that this is a network-inactivity timeout and not an overall deadline for the complete HTTP request."}, {"action": "ACCEPT", "version_id": "0b28bf9b-68e4-4597-8d02-88fc255ea0f4", "reason": null}]`

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
- V2 (sarvam, sha256 `4787ccf716743195fc9f8b3c20416cbe993f3164eca1aa862d8ae31f09cf84cf`):

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of network inactivity. This timeout applies to periods when no data is being transmitted, not to the total duration of the request.
  ```

### Scenario 6: Human-modify a persisted UPDATE, accept it, and apply it without a Sarvam rewrite

Result: **PASS**  
Expected: **UPDATE**  
Actual: **UPDATE**  
Case: `8ed22ce0-07a4-454c-aa6d-1b79d6dc213a`  

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sarvam section decisions:
- `docs/advanced/timeouts.md::__intro__`: **UPDATE** — 
  Evidence completeness: **n/a**; safe claims: []; unsupported claims: []

  Proposed text:

  ```markdown
  The default timeout is 8 seconds of network inactivity.
  
  This setting does not impose an overall deadline for the complete HTTP request.
  ```

Sarvam call diagnostics:

Human actions: `[{"action": "MODIFY", "version_id": "c3022a83-a568-41b1-9555-918209dd2f67", "content": "The default timeout is 8 seconds of network inactivity.\n\nThis setting does not impose an overall deadline for the complete HTTP request.\n"}, {"action": "ACCEPT", "version_id": "c3022a83-a568-41b1-9555-918209dd2f67", "content": null}]`

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
