import pytest

from docsync.engine import aggregate_case_decision
from docsync.models import Decision


@pytest.mark.parametrize(
    ("sections", "expected"),
    [
        ([Decision.UPDATE], Decision.UPDATE),
        ([Decision.NO_CHANGE, Decision.UPDATE], Decision.UPDATE),
        ([Decision.UNCERTAIN], Decision.UNCERTAIN),
        ([Decision.NO_CHANGE, Decision.UNCERTAIN], Decision.UNCERTAIN),
        ([Decision.NO_CHANGE, Decision.NO_CHANGE], Decision.NO_CHANGE),
    ],
)
def test_case_workflow_state_is_aggregated_from_section_decisions(sections, expected):
    assert aggregate_case_decision(sections) == expected


def test_case_workflow_aggregation_accepts_serialized_decisions():
    assert aggregate_case_decision(["NO_CHANGE", "UNCERTAIN"]) == Decision.UNCERTAIN
