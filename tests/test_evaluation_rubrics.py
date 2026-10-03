from scripts.run_httpx_evaluation import revision_addresses_feedback


def test_revision_feedback_rubric_accepts_explicit_deadline_wording():
    text = "The timeout covers network inactivity, not an overall deadline for the complete HTTP request."
    assert revision_addresses_feedback(text)


def test_revision_feedback_rubric_accepts_semantic_total_duration_paraphrase():
    text = "The default is a timeout after 8 seconds of network inactivity. This timeout applies while no data is being transmitted, not to the total duration of the request."
    assert revision_addresses_feedback(text)


def test_revision_feedback_rubric_requires_network_inactivity_and_request_scope():
    assert not revision_addresses_feedback("The request has no overall deadline.")
    assert not revision_addresses_feedback("The timeout covers network inactivity.")
