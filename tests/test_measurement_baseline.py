from datetime import timedelta
import pytest
from test_online_phase2 import system, make_case
from docsync.evaluation.metrics import ratio, binary_scores, decision_scores, recall_at_k, distribution, review_action_rates
from docsync.evaluation.live import report
from docsync.web.models import Repository, AuditEvent, SarvamCall, ReviewAction, Job, utcnow


def test_equal_timestamp_audit_events_keep_attempt_order(tmp_path, monkeypatch):
    from docsync.store import Store
    monkeypatch.setattr('docsync.store.now', lambda: '2026-10-04T00:00:00+00:00')
    store = Store(tmp_path / 'ordered.sqlite3')
    try:
        case_id = store.create_case({'repo_root': str(tmp_path), 'old_sha': 'a' * 40,
            'new_sha': 'b' * 40, 'mappings': [], 'sections': []})
        for attempt in range(3):
            store.event('sarvam_call', {'attempt': attempt}, case_id)
        import json
        assert [json.loads(e['payload_json'])['attempt'] for e in store.audit(case_id)
            if e['kind'] == 'sarvam_call'] == [0, 1, 2]
    finally:
        store.db.close()


def test_zero_denominators_are_unknown_and_never_perfect():
    assert ratio(0, 0)['value'] is None
    assert binary_scores(0, 0, 0, 0)['f1']['value'] is None
    assert decision_scores({}, {})['accuracy']['value'] is None
    assert distribution([])['p95'] is None
    assert recall_at_k([], 5)['value'] is None
    for values in [(1, 0), (-1, 2), (1.5, 2), (True, 2)]:
        with pytest.raises(ValueError): ratio(*values)


def test_missing_positive_predictions_count_as_missed_impact():
    expected = {'update': 'UPDATE', 'miss': 'UPDATE', 'abstain': 'UPDATE', 'missing': 'UPDATE',
        'correct_negative': 'NO_CHANGE', 'false_positive': 'NO_CHANGE', 'uncertain_label': 'UNCERTAIN'}
    predicted = {'update': 'UPDATE', 'miss': 'NO_CHANGE', 'abstain': 'UNCERTAIN',
        'correct_negative': 'NO_CHANGE', 'false_positive': 'UPDATE', 'uncertain_label': 'UPDATE', 'unlabelled': 'UPDATE'}
    result = decision_scores(expected, predicted)
    assert result['counts'] == {'tp': 1, 'fp': 1, 'fn': 3, 'tn': 1}
    assert result['recall']['value'] == .25
    assert result['precision']['value'] == .5
    assert result['false_negative_rate']['value'] == .75
    assert result['strict_no_change_false_negative_rate']['value'] == .25
    assert result['confusion_matrix']['UPDATE']['MISSING'] == 1
    assert result['unlabelled_prediction_ids'] == ['unlabelled']
    assert result['accuracy']['denominator'] == 7


def test_retrieval_metric_deduplicates_chunks_and_reports_unlabelled_queries():
    result = recall_at_k([{'relevant_section_ids': ['a', 'b'], 'retrieved_section_ids': ['a', 'a', 'x']},
        {'relevant_section_ids': ['b'], 'retrieved_section_ids': ['b']},
        {'relevant_section_ids': [], 'retrieved_section_ids': ['unknown']}], 2)
    assert result['value'] == .75 and result['queries_scored'] == 2
    assert result['queries_without_relevance_labels'] == 1


def test_nearest_rank_latency_does_not_convert_missing_data_to_zero():
    result = distribution([1, 2, 3, 100, None, -1, float('inf')])
    assert result['median'] == 2.5 and result['p95'] == 100
    assert result['samples'] == 4 and result['missing_or_invalid'] == 3


def test_review_rates_use_documented_event_denominator():
    rates = review_action_rates(['ACCEPT', 'MODIFY', 'REJECT', 'ACCEPT', 'UNKNOWN'])
    assert rates['accept']['value'] == .5
    assert rates['modify']['denominator'] == 4


def test_live_measurements_are_scoped_and_contain_no_text_or_semantic_labels(system):
    _, _, factory, repo_id = system
    with factory() as session:
        case, _, proposal, version = make_case(session, repo_id)
        other = Repository(full_name='other/project', monitored_branch='main')
        session.add(other); session.flush()
        foreign, *_ = make_case(session, other.id)
        now = utcnow()
        case.created_at = now - timedelta(seconds=10)
        session.add(AuditEvent(case_id=case.id, kind='analysis_completed', created_at=now, payload={}))
        session.add(SarvamCall(case_id=case.id, operation='impact', metadata_json={'latency_ms': 500}))
        session.add(SarvamCall(case_id=foreign.id, operation='impact', metadata_json={'latency_ms': 9000}))
        session.add(ReviewAction(proposal_id=proposal.id, action='ACCEPT', version_id=version.id))
        session.add(Job(repo_id=repo_id, kind='analyze_push', payload={}, status='ERROR', attempts=2))
        session.commit()
        result = report(session, repo_id)
        assert result['counts']['cases'] == 1 and result['counts']['impact_provider_attempts'] == 1
        assert result['impact_attempt_latency_ms']['median'] == 500
        assert result['intake_to_first_review_ready_seconds']['median'] == 10
        assert result['analysis_terminal_job_failure_rate']['value'] == 1
        assert result['analysis_retried_job_rate']['value'] == 1
        assert result['quality_metrics'] is None and result['estimated_cost'] is None
        assert 'proposed_text' not in str(result) and 'question' not in result
