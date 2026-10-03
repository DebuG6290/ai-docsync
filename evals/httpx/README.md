# HTTPX Phase 1 evaluation

The testbed is a local clone of `encode/httpx`, pinned at the commit in `PINNED_COMMIT.txt`. The original clone is ignored by Git. The scenario preparation script creates separate local repositories and source commits under `.httpx-scenarios/`; it refuses to overwrite existing repositories.

## Run the HTTPX fork tests

Install the project and HTTPX test dependencies in a virtual environment, then run HTTPX's own timeout and configuration tests against the pinned source tree:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]' -e '.\.httpx-testbed' -r requirements-httpx-test.txt
.\.venv\Scripts\python.exe -m pytest .httpx-testbed\tests\test_timeouts.py .httpx-testbed\tests\test_config.py -q -k "not write_timeout" -m "not network"
```

These are HTTPX's real tests and run its code; the local DocSync unit tests are additional infrastructure checks. The 100 MB write-timeout test is excluded because it does not time out on this Windows socket stack, and the external-IP connect test is excluded because it requires network access.

## Prepare controlled commits

```powershell
.\.venv\Scripts\python.exe scripts\prepare_httpx_scenarios.py --output .httpx-scenarios-demo
```

The four scenarios cover a default change, behavior-preserving refactor, public property addition, and an external runtime policy whose value is unavailable in the repository.

## Live Sarvam run

Set `SARVAM_API_KEY` in the process environment used by the command. DocSync itself reads only `SARVAM_API_KEY` from the process environment and does not load a project `.env` file. The adapter uses Sarvam V1 `response_format.type=json_schema` with `strict=true`, Pydantic validation, operation-specific output-token budgets, and `reasoning_effort=null`. It records response-shape, finish-reason, token-usage, validation, retry, latency, and error-category diagnostics without recording the API key or reasoning text.

```powershell
.\.venv\Scripts\python.exe scripts\run_httpx_evaluation.py --manifest .httpx-scenarios-demo\manifest.json --db .docsync-state\httpx-demo.sqlite3 --out evals\httpx\demo-report.md
```

Reports are written to `evals/httpx/demo-report.md` and `.json`; call metadata, decisions, proposals, revisions, review actions, and apply hashes are in `.docsync-state/httpx-demo.sqlite3`. Report results distinguish `PASS`, `SEMANTIC_FAIL`, `MODEL_CONTRACT_ERROR`, `API_ERROR`, and `SYSTEM_ERROR`. Scenario 5 requires V2 to clarify that the inactivity timeout is not an overall request deadline. Scenario 6 clones the persisted successful UPDATE case into an isolated repository, checks a human edit without another Sarvam analysis call, explicitly accepts it, then applies and verifies the exact text and hashes.

## Normal CLI workflow

From this workspace, supply the HTTPX repository with `--repo` and a SQLite path with `--db`:

```powershell
.\.venv\Scripts\python.exe -m docsync --db .docsync-state/docsync.sqlite3 map suggest --repo .httpx-testbed --rev b5addb64f0161ff6bfe94c124ef76f6a1fba5254 --code-path httpx/_config.py --docs docs/advanced/timeouts.md docs/quickstart.md
.\.venv\Scripts\python.exe -m docsync --db .docsync-state/docsync.sqlite3 map pending
.\.venv\Scripts\python.exe -m docsync --db .docsync-state/docsync.sqlite3 map confirm SUGGESTION_ID
.\.venv\Scripts\python.exe -m docsync --db .docsync-state/docsync.sqlite3 analyze --repo .httpx-scenarios/scenario-1-repo --old OLD_SHA --new NEW_SHA
.\.venv\Scripts\python.exe -m docsync --db .docsync-state/docsync.sqlite3 review CASE_ID
.\.venv\Scripts\python.exe -m docsync --db .docsync-state/docsync.sqlite3 apply CASE_ID
.\.venv\Scripts\python.exe -m docsync --db .docsync-state/docsync.sqlite3 audit CASE_ID
```

The initial evaluation mappings are a controlled, operator-confirmed baseline and are limited to those experiments. They do not encode expected impact decisions.
