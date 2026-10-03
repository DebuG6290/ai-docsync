import pytest

from docsync.errors import ModelError
from docsync.models import Decision, ImpactResponse
from docsync.sarvam import ModelClient, SarvamClient


class StaticClient(ModelClient):
    def __init__(self, response: str):
        self.response = response

    def complete(self, system: str, user: str, schema_name: str, schema: dict) -> str:
        return self.response


def test_structured_schema_requires_every_property_for_strict_json_output():
    schema = ImpactResponse.model_json_schema()
    assert set(schema["properties"]) == set(schema["required"])
    nested = schema["$defs"]["SectionAnalysis"]
    assert set(nested["properties"]) == set(nested["required"])
    assert "current_text" not in nested["properties"]
    assert "case_decision" not in schema["properties"]
    assert "evidence_completeness" in nested["properties"]
    assert "safe_claims" in nested["properties"]
    assert "unsupported_claims" in nested["properties"]
    assert set(schema["$defs"]["EvidenceCompleteness"]["enum"]) == {"COMPLETE", "PARTIAL", "INSUFFICIENT"}
    assert "decision" in nested["properties"]


def test_malformed_model_content_fails_validation_after_single_repair_attempt():
    client = StaticClient('{"decision":"UPDATE","sections":[]}')
    with pytest.raises(ModelError, match="schema-invalid"):
        client.structured("system", "user", ImpactResponse, "impact_analysis")


def test_unparseable_model_content_fails_validation_without_repair():
    client = StaticClient("not JSON")
    with pytest.raises(ModelError, match="schema-invalid"):
        client.structured("system", "user", ImpactResponse, "impact_analysis")


class SequenceClient(ModelClient):
    def __init__(self, responses):
        self.responses = list(responses)
        self.users = []

    def complete(self, system: str, user: str, schema_name: str, schema: dict) -> str:
        self.users.append(user)
        return self.responses.pop(0)


def _no_change(section_id: str) -> str:
    import json

    return json.dumps(
        {
            "summary": "The refactor preserves documented behavior.",
            "sections": [
                {
                    "section_id": section_id,
                    "decision": "NO_CHANGE",
                    "proposed_text": None,
                    "reason": "The public behavior is unchanged.",
                    "code_evidence": ["Timeout.as_dict still returns the same fields."],
                    "evidence_completeness": "COMPLETE",
                    "missing_information": [],
                    "safe_claims": ["The same four timeout fields are returned."],
                    "unsupported_claims": [],
                }
            ],
        }
    )


def test_candidate_set_contract_gets_one_targeted_repair_retry():
    import json

    expected_id = "docs/advanced/timeouts.md::__intro__"
    first = json.dumps(
        {
            "summary": "No change.",
            "sections": [],
        }
    )
    client = SequenceClient([first, _no_change(expected_id)])
    diagnostics = []

    result = client.structured(
        "system",
        '{"candidate_section_ids": ["docs/advanced/timeouts.md::__intro__"]}',
        ImpactResponse,
        "impact_analysis",
        operation="impact",
        prompt_version="impact.v4",
        candidate_section_ids=[expected_id],
        diagnostic_sink=diagnostics.append,
        contract_validator=lambda response: (
            None
            if [section.section_id for section in response.sections] == [expected_id]
            else f"expected exactly candidate section IDs { [expected_id] }"
        ),
    )

    assert result.sections[0].decision == Decision.NO_CHANGE
    assert len(client.users) == 2
    assert expected_id in client.users[1]
    assert "previous_attempt_error" in client.users[1]
    assert [item["retry_count"] for item in diagnostics] == [0, 1]
    assert diagnostics[0]["response_contract_validation"] == "failed"
    assert diagnostics[1]["response_contract_validation"] == "passed"


def test_contract_failure_is_reported_as_model_contract_error_after_one_retry():
    client = SequenceClient(["not JSON", "still not JSON"])
    with pytest.raises(ModelError) as caught:
        client.structured("system", "user", ImpactResponse, "impact_analysis")

    assert caught.value.category == "MODEL_CONTRACT_ERROR"
    assert len(client.users) == 2


def test_response_diagnostics_capture_shape_and_usage_without_reasoning_text():
    payload = {
        "id": "completion-id",
        "object": "chat.completion",
        "model": "sarvam-105b",
        "choices": [
            {
                "finish_reason": "length",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": "this private reasoning must not be persisted",
                    "tool_calls": None,
                    "refusal": None,
                },
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 4096, "total_tokens": 4196},
    }

    diagnostic = SarvamClient._response_shape(payload)

    assert diagnostic["response_type"] == "dict"
    assert diagnostic["choices_count"] == 1
    assert diagnostic["finish_reason"] == "length"
    assert diagnostic["message_type"] == "dict"
    assert diagnostic["content_type"] == "NoneType"
    assert diagnostic["reasoning_content_present"] is True
    assert diagnostic["tool_calls_present"] is True
    assert diagnostic["input_tokens"] == 100
    assert diagnostic["output_tokens"] == 4096
    assert "reasoning_content" not in diagnostic

