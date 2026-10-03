from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from docsync.errors import ModelError

T = TypeVar("T", bound=BaseModel)

MODEL_CONTRACT_ERROR = "MODEL_CONTRACT_ERROR"
API_ERROR = "API_ERROR"

OUTPUT_TOKEN_BUDGETS = {"mapping": 4096, "impact": 8192, "revision": 4096, "conflict": 4096}


def _type_name(value: Any) -> str:
    return type(value).__name__


def _validation_error(exc: ValidationError) -> str:
    errors = exc.errors(include_input=False)
    if not errors:
        return "Sarvam output failed Pydantic validation"
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ())) or "response"
    return f"Sarvam structured output failed Pydantic validation at {location}: {first.get('msg', 'invalid value')}"


class ModelClient:
    """Structured output boundary shared by the provider and deterministic test clients."""

    last_response_diagnostics: dict[str, Any]

    def complete(self, system: str, user: str, schema_name: str, schema: dict) -> str:
        raise NotImplementedError

    def structured(
        self,
        system: str,
        user: str,
        response_type: type[T],
        schema_name: str,
        *,
        operation: str = "impact",
        prompt_version: str = "unspecified",
        candidate_section_ids: list[str] | None = None,
        diagnostic_sink: Callable[[dict[str, Any]], None] | None = None,
        contract_validator: Callable[[T], str | None] | None = None,
    ) -> T:
        """Call Sarvam, validate the typed output, and make at most one repair retry.

        Retries repair transport/format/output-contract failures only, excluding
        known length truncation, which cannot be repaired at the same budget. The caller's
        validator must check mechanical response requirements, never semantic
        documentation impact.
        """
        model = getattr(self, "model", type(self).__name__)
        schema = response_type.model_json_schema()
        retry_user = user
        last_error: ModelError | None = None

        for attempt in range(2):
            started = time.perf_counter()
            diagnostic: dict[str, Any] = {
                "operation": operation,
                "model": model,
                "prompt_version": prompt_version,
                "candidate_section_ids": candidate_section_ids or [],
                "finish_reason": None,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "response_contract_validation": "pending",
                "retry_count": attempt,
            }
            self.last_response_diagnostics = {}
            try:
                raw = self.complete(system, retry_user, schema_name, schema)
                diagnostic.update(self.last_response_diagnostics)
                try:
                    result = response_type.model_validate_json(raw)
                except ValidationError as exc:
                    raise ModelError(
                        f"Sarvam returned malformed or schema-invalid {schema_name}: {_validation_error(exc)}",
                        category=MODEL_CONTRACT_ERROR,
                        diagnostics=self.last_response_diagnostics,
                    ) from exc

                contract_error = contract_validator(result) if contract_validator else None
                if contract_error:
                    raise ModelError(
                        contract_error,
                        category=MODEL_CONTRACT_ERROR,
                        diagnostics=self.last_response_diagnostics,
                    )

                diagnostic["response_contract_validation"] = "passed"
                diagnostic["error_category"] = None
                diagnostic["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
                self._record(diagnostic, diagnostic_sink)
                return result
            except ModelError as exc:
                last_error = exc
                diagnostic.update(self.last_response_diagnostics)
                diagnostic.update(exc.diagnostics)
                diagnostic["error_category"] = exc.category
                diagnostic["response_contract_validation"] = (
                    "failed" if exc.category == MODEL_CONTRACT_ERROR else "not_run"
                )
                diagnostic["error"] = str(exc)
                diagnostic["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)

                # The same output scope/budget cannot repair a known truncation.
                # Fail explicitly; orchestration bounds impact scope before calling.
                can_retry = diagnostic.get('finish_reason') != 'length' and attempt == 0 and (
                    exc.category == MODEL_CONTRACT_ERROR or exc.retryable
                )
                diagnostic["retry_scheduled"] = can_retry
                self._record(diagnostic, diagnostic_sink)
                if not can_retry:
                    raise

                if exc.category == MODEL_CONTRACT_ERROR:
                    repair = {
                        "response_contract_retry": {
                            "previous_attempt_error": str(exc),
                            "required_candidate_section_ids": candidate_section_ids or [],
                            "instruction": (
                                "Return one complete response matching the supplied JSON Schema. "
                                "For candidate sections, include each required section_id exactly once. "
                                "Do not include commentary or markdown fences."
                            ),
                        }
                    }
                    retry_user = user + "\n\n" + json.dumps(repair, ensure_ascii=False)
                else:
                    time.sleep(0.5)

        assert last_error is not None
        raise last_error

    @staticmethod
    def _record(
        diagnostic: dict[str, Any],
        sink: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        if sink is not None:
            sink(dict(diagnostic))


class SarvamClient(ModelClient):
    """Sarvam V1 Chat Completions adapter. Keys and raw reasoning are never persisted."""

    def __init__(self, model: str = "sarvam-105b", timeout: int = 120):
        self.model = model
        self.timeout = timeout
        self.last_response_diagnostics = {}
        self._active_operation = "impact"

    def complete(self, system: str, user: str, schema_name: str, schema: dict) -> str:
        key = os.environ.get("SARVAM_API_KEY")
        if not key:
            raise ModelError(
                "SARVAM_API_KEY is not set; no live Sarvam call was made",
                category=API_ERROR,
            )

        operation = self._active_operation
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": OUTPUT_TOKEN_BUDGETS.get(operation, 4096),
            # Sarvam documents that reasoning tokens share max_tokens and can leave
            # message.content empty. This application needs the structured answer only.
            "reasoning_effort": None,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        request = urllib.request.Request(
            "https://api.sarvam.ai/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"api-subscription-key": key, "Content-Type": "application/json"},
            method="POST",
        )
        self.last_response_diagnostics = {
            "request_model": self.model,
            "request_format": "json_schema",
            "schema_name": schema_name,
            "max_tokens": body["max_tokens"],
            "reasoning_effort": None,
            "response_type": "not_received",
            "choices_count": None,
            "message_type": None,
            "content_type": None,
            "reasoning_content_present": False,
            "reasoning_content_nonempty": False,
            "tool_calls_present": False,
            "tool_calls_nonempty": False,
            "refusal_present": False,
            "finish_reason": None,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        }

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw_body = response.read()
                payload = json.loads(raw_body.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            request_id = None
            if exc.headers is not None:
                request_id = exc.headers.get("x-request-id") or exc.headers.get("request-id")
            self.last_response_diagnostics.update(
                http_status=exc.code,
                response_request_id=request_id,
                response_type="http_error",
            )
            retryable = exc.code in {408, 429} or exc.code >= 500
            raise ModelError(
                f"Sarvam API returned HTTP {exc.code}",
                category=API_ERROR,
                retryable=retryable,
                diagnostics=self.last_response_diagnostics,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.last_response_diagnostics["transport_error_type"] = type(exc).__name__
            raise ModelError(
                f"Sarvam transport failed: {type(exc).__name__}",
                category=API_ERROR,
                retryable=True,
                diagnostics=self.last_response_diagnostics,
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.last_response_diagnostics.update(
                response_type="invalid_json_envelope",
                envelope_error_type=type(exc).__name__,
            )
            raise ModelError(
                "Sarvam returned a non-JSON or undecodable response envelope",
                category=MODEL_CONTRACT_ERROR,
                diagnostics=self.last_response_diagnostics,
            ) from exc

        self.last_response_diagnostics.update(self._response_shape(payload))
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or len(choices) != 1:
            raise ModelError(
                "Sarvam response must contain exactly one choice",
                category=MODEL_CONTRACT_ERROR,
                diagnostics=self.last_response_diagnostics,
            )

        choice = choices[0]
        if not isinstance(choice, dict):
            raise ModelError(
                "Sarvam choice has an invalid response shape",
                category=MODEL_CONTRACT_ERROR,
                diagnostics=self.last_response_diagnostics,
            )
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            raise ModelError(
                "Sarvam output was truncated because finish_reason=length",
                category=MODEL_CONTRACT_ERROR,
                diagnostics=self.last_response_diagnostics,
            )
        if finish_reason != "stop":
            raise ModelError(
                f"Sarvam completion did not finish normally (finish_reason={finish_reason!r})",
                category=MODEL_CONTRACT_ERROR,
                diagnostics=self.last_response_diagnostics,
            )

        message = choice.get("message")
        if not isinstance(message, dict):
            raise ModelError(
                "Sarvam choice message has an invalid response shape",
                category=MODEL_CONTRACT_ERROR,
                diagnostics=self.last_response_diagnostics,
            )
        if message.get("tool_calls"):
            raise ModelError(
                "Sarvam requested tool calls; this operation expects structured message content",
                category=MODEL_CONTRACT_ERROR,
                diagnostics=self.last_response_diagnostics,
            )
        content = message.get("content")
        if not isinstance(content, str):
            raise ModelError(
                f"Sarvam message.content type was {self.last_response_diagnostics.get('content_type')}; expected string",
                category=MODEL_CONTRACT_ERROR,
                diagnostics=self.last_response_diagnostics,
            )
        return content

    def structured(self, *args, **kwargs):
        self._active_operation = kwargs.get("operation", "impact")
        return super().structured(*args, **kwargs)

    @staticmethod
    def _response_shape(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {
                "response_type": _type_name(payload),
                "choices_count": None,
                "response_object": None,
                "response_id": None,
                "response_model": None,
                "finish_reason": None,
                "message_type": None,
                "content_type": None,
                "reasoning_content_present": False,
                "reasoning_content_nonempty": False,
                "tool_calls_present": False,
                "tool_calls_nonempty": False,
                "refusal_present": False,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
            }

        choices = payload.get("choices")
        choices_count = len(choices) if isinstance(choices, list) else None
        choice = choices[0] if isinstance(choices, list) and choices else None
        message = choice.get("message") if isinstance(choice, dict) else None
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        return {
            "response_type": _type_name(payload),
            "response_object": payload.get("object"),
            "response_id": payload.get("id"),
            "response_model": payload.get("model"),
            "response_created": payload.get("created"),
            "system_fingerprint": payload.get("system_fingerprint"),
            "choices_count": choices_count,
            "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
            "message_type": _type_name(message) if message is not None else None,
            "content_type": _type_name(content),
            "content_length": len(content) if isinstance(content, str) else None,
            "reasoning_content_present": bool(
                isinstance(message, dict) and "reasoning_content" in message
            ),
            "reasoning_content_nonempty": bool(
                isinstance(message, dict) and message.get("reasoning_content")
            ),
            "tool_calls_present": bool(isinstance(message, dict) and "tool_calls" in message),
            "tool_calls_nonempty": bool(isinstance(message, dict) and message.get("tool_calls")),
            "refusal_present": bool(
                isinstance(message, dict) and message.get("refusal")
            ),
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
