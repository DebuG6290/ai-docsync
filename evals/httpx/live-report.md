# HTTPX Live Evaluation

Generated: 2026-10-02T22:05:46.733758+00:00
Pinned base: `b5addb64f0161ff6bfe94c124ef76f6a1fba5254`

## Scenario 1: Default timeout changes from five to eight seconds

Expected: **UPDATE**  
Actual: **UPDATE**  
Result: **PASS**

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sections Sarvam considered:
- `docs/advanced/timeouts.md::__intro__` — **UPDATE**

  Current text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 5 seconds of
  network inactivity.
  ```

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of
  network inactivity.
  ```

  Reason: The intro states the package default is 5 seconds, but the code now defines `DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=8.0)`.
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client` — **UPDATE**

  Current text:

  ```markdown
  ## Setting a default timeout on a client
  
  You can set a timeout on a client instance, which results in the given
  `timeout` being used as the default for requests made with this client:
  
  ```python
  client = httpx.Client()              # Use a default 5s timeout everywhere.
  client = httpx.Client(timeout=10.0)  # Use a default 10s timeout everywhere.
  client = httpx.Client(timeout=None)  # Disable all timeouts by default.
  ```
  ```

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

  Reason: The first example relies on the package default timeout; the comment claiming 5s is now inconsistent with `DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=8.0)`.
- `docs/quickstart.md::timeouts` — **UPDATE**

  Current text:

  ```markdown
  ## Timeouts
  
  HTTPX defaults to including reasonable timeouts for all network operations,
  meaning that if a connection is not properly established then it should always
  raise an error rather than hanging indefinitely.
  
  The default timeout for network inactivity is five seconds. You can modify the
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

  Reason: The quickstart explicitly states the network-inactivity default is five seconds, which no longer matches `DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=8.0)`.

Human actions: []
Revision count: 0

Final text:

```markdown
(not applied)
```

## Scenario 2: Internal Timeout.as_dict refactor preserves behavior

Expected: **NO_CHANGE**  
Actual: **ERROR**  
Result: **FAIL**

Error: ModelError: Sarvam response omitted, duplicated, or introduced candidate section IDs

Mapped candidate sections:
- `docs/advanced/timeouts.md::fine-tuning-the-configuration`

Sections Sarvam considered:

Human actions: []
Revision count: 0

Final text:

```markdown
(not applied)
```

## Scenario 3: Timeout.is_disabled public property added

Expected: **UPDATE**  
Actual: **ERROR**  
Result: **FAIL**

Error: ModelError: Sarvam response content was not text

Mapped candidate sections:
- `docs/advanced/timeouts.md::setting-and-disabling-timeouts`

Sections Sarvam considered:

Human actions: []
Revision count: 0

Final text:

```markdown
(not applied)
```

## Scenario 4: Default timeout comes from an unavailable external runtime policy

Expected: **UNCERTAIN**  
Actual: **ERROR**  
Result: **FAIL**

Error: ModelError: Sarvam returned malformed or schema-invalid impact_analysis: 1 validation error for ImpactResponse
  Invalid JSON: EOF while parsing a string at line 1 column 2884 [type=json_invalid, input_value='{"decision":"NO_CHANGE",...\n>>> httpx.get(\'https', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/json_invalid

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sections Sarvam considered:

Human actions: []
Revision count: 0

Final text:

```markdown
(not applied)
```

## Scenario 5: Reject one proposal with network-inactivity feedback; leave other sections unchanged

Expected: **UPDATE**  
Actual: **UPDATE**  
Result: **PASS**

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sections Sarvam considered:
- `docs/advanced/timeouts.md::__intro__` — **UPDATE**

  Current text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 5 seconds of
  network inactivity.
  ```

  Proposed text:

  ```markdown
  HTTPX is careful to enforce timeouts everywhere by default.
  
  The default behavior is to raise a `TimeoutException` after 8 seconds of
  network inactivity.
  ```

  Reason: The intro states the package default is 5 seconds, but the code now defines `DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=8.0)`.

Human actions: [{"action": "REJECT", "reason": "The new timeout value is correct, but the wording should also preserve the explanation that this timeout measures network inactivity.", "version_id": "43284bda-3ad8-4e25-a703-98b6bef4f1df"}, {"action": "ACCEPT", "reason": null, "version_id": "286da05d-ef8a-4b0d-8f88-b0ba668c3ee4"}]
Revision count: 1

Final text:

```markdown
HTTPX is careful to enforce timeouts everywhere by default.

The default behavior is to raise a `TimeoutException` after 8 seconds of
network inactivity.
```

## Scenario 6: Human-modify a proposal, explicitly accept, then apply the human-authored version

Expected: **UPDATE**  
Actual: **ERROR**  
Result: **FAIL**

Error: ModelError: Sarvam response content was not text

Mapped candidate sections:
- `docs/advanced/timeouts.md::__intro__`
- `docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client`
- `docs/quickstart.md::timeouts`

Sections Sarvam considered:

Human actions: []
Revision count: 0

Final text:

```markdown
(not applied)
```
