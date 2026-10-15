from types import SimpleNamespace as NS

import pytest

from docsync.ui.change_trace import build_change_trace, load_change_trace
from docsync.web.models import AuditEvent, KnowledgeVersion, ProposalVersion, Repository, utcnow
from test_online_phase2 import make_case, system


def item(*, decision='UPDATE', proposal=True, accepted=False, release_status=None):
    case = NS(id='case', repo_id='repo', before_sha='a' * 40, after_sha='b' * 40,
        case_data={'mappings': [{'section_id': 'guide.md::section'}]})
    section = NS(case_id='case', section_id='guide.md::section', decision=decision, human_resolution=None)
    proposals = [NS(id='proposal', case_id='case', section_id=section.section_id,
        status='ACCEPTED' if accepted else 'PENDING', accepted_version_id='approved' if accepted else None)] if proposal else []
    release = NS(case_id='case', repo_id='repo', status=release_status, pr_number=4,
        pr_url='https://github.com/owner/repo/pull/4', commit_sha='c' * 40, merged_sha=None,
        activated_at=None) if release_status else None
    return {'case': case, 'sections': [section], 'proposals': proposals, 'release': release}


def steps(record, **kwargs):
    return {s.title: s for s in build_change_trace('repo', record, **kwargs)}


def activation_evidence(record):
    release = record['release']
    release.merged_sha = 'd' * 40
    release.activated_at = utcnow()
    events = [NS(case_id='case', kind='documentation_merge_verified',
        payload={'pr_number': 4, 'merged_sha': release.merged_sha}),
        NS(case_id='case', kind='knowledge_index_activated',
            payload={'version_id': 'actual', 'merged_sha': release.merged_sha})]
    versions = [NS(id='actual', repo_id='repo', source_commit=release.merged_sha),
        NS(id='newer', repo_id='repo', source_commit='e' * 40)]
    return {'audit_events': events, 'knowledge_versions': versions,
        'active_version_id': 'newer', 'version_names': {'actual': 'K2', 'newer': 'K3'}}


def test_pending_trace_never_claims_publication_or_activation():
    trace = steps(item())
    assert trace['Human approval'].state == 'Pending'
    assert trace['Documentation PR'].state == 'Pending'
    assert trace['Merge verification'].state == 'Not merged'
    assert trace['Knowledge activation'].state == 'Not verified'
    assert 'a' * 40 in trace['Code change'].details[0]
    assert trace['Mapped documentation'].details[-1] == 'guide.md::section: UPDATE'


def test_unassessed_mapping_and_no_change_are_distinct():
    record = item(decision='NO_CHANGE', proposal=False)
    trace = steps(record)
    assert trace['Human approval'].state == 'No update required'
    assert trace['Documentation PR'].state == 'Not required'
    assert trace['Knowledge activation'].state == 'Not verified'
    record['sections'] = []
    trace = steps(record)
    assert trace['Mapped documentation'].state == 'Pending'
    assert trace['Mapped documentation'].details[-1] == 'guide.md::section: Not assessed'
    assert trace['Human approval'].state == 'Pending'


def test_partial_assessment_and_unmapped_changes_are_visible():
    record = item(decision='NO_CHANGE', proposal=False)
    record['case'].case_data['mappings'].append({'section_id': 'guide.md::missing'})
    record['case'].case_data['changes'] = [{'code_id': 'pkg/new.py::unmapped'}]
    trace = steps(record)
    assert trace['Mapped documentation'].state == 'Partially assessed'
    assert 'guide.md::missing: Not assessed' in trace['Mapped documentation'].details
    assert 'pkg/new.py::unmapped: No approved mapping; not assessed' in trace['Mapped documentation'].details
    assert trace['Human approval'].state == 'Pending'


def test_unmapped_change_does_not_turn_partial_no_change_into_an_all_clear():
    record = item(decision='NO_CHANGE', proposal=False)
    record['case'].case_data['changes'] = [{'code_id': 'pkg/new.py::unmapped'}]
    trace = steps(record)
    assert trace['Mapped documentation'].state == 'Partially assessed'
    assert trace['Human approval'].state == 'Pending'
    assert trace['Documentation PR'].state == 'Pending'


def test_accepted_version_is_exact_and_not_replaced_by_newer_version():
    versions = [NS(id='approved', proposal_id='proposal', version=2),
        NS(id='newer', proposal_id='proposal', version=3)]
    approval = steps(item(accepted=True), proposal_versions=versions)['Human approval']
    assert approval.state == 'Approved'
    assert approval.details == ('guide.md::section: Version 2 (approved)',)


def test_accepted_id_must_belong_to_this_proposal():
    versions = [NS(id='approved', proposal_id='other-proposal', version=99)]
    approval = steps(item(accepted=True), proposal_versions=versions)['Human approval']
    assert approval.state == 'Pending'
    assert 'could not be verified' in approval.details[0]


def test_missing_update_proposal_cannot_make_partial_approval_complete():
    record = item(accepted=True)
    record['sections'].append(NS(case_id='case', section_id='guide.md::another',
        decision='UPDATE', human_resolution=None))
    approval = steps(record, proposal_versions=[NS(id='approved', proposal_id='proposal', version=2)])['Human approval']
    assert approval.state == 'Pending'
    assert any('another: no proposal version recorded' in detail for detail in approval.details)


def test_merged_commit_and_same_source_version_do_not_imply_activation():
    record = item(release_status='MERGED')
    evidence = activation_evidence(record)
    evidence['audit_events'] = []
    trace = steps(record, **evidence)
    assert trace['Merge verification'].state == 'Merge recorded'
    assert trace['Knowledge activation'].state == 'Not verified'


def test_indexed_trace_displays_actual_historical_version_not_current_version():
    record = item(release_status='INDEXED')
    trace = steps(record, **activation_evidence(record))
    assert trace['Merge verification'].state == 'Verified'
    activation = trace['Knowledge activation']
    assert activation.state == 'Verified'
    assert activation.details[0] == 'K2 · actual'
    assert 'Historical activation' in activation.details[-1]
    assert all('K3' not in detail for detail in activation.details)


@pytest.mark.parametrize('tamper', ['repo', 'case', 'commit', 'merge_event', 'timestamp'])
def test_activation_requires_matching_repository_release_and_audit_evidence(tamper):
    record = item(release_status='INDEXED')
    evidence = activation_evidence(record)
    if tamper == 'repo':
        evidence['knowledge_versions'][0].repo_id = 'other-repo'
    elif tamper == 'case':
        evidence['audit_events'][1].case_id = 'other-case'
    elif tamper == 'commit':
        evidence['audit_events'][1].payload['merged_sha'] = 'f' * 40
    elif tamper == 'merge_event':
        evidence['audit_events'][0].payload['pr_number'] = 99
    else:
        record['release'].activated_at = None
    assert steps(record, **evidence)['Knowledge activation'].state == 'Not verified'


@pytest.mark.parametrize('status,expected', [('CLOSED', 'Not verified'), ('INDEX_ERROR', 'Needs attention'),
    ('INDEX_CONFLICT', 'Needs attention'), ('KNOWLEDGE_REVIEW', 'Needs attention')])
def test_closed_and_failed_releases_do_not_claim_activation(status, expected):
    record = item(release_status=status)
    evidence = activation_evidence(record)
    trace = steps(record, **evidence)
    assert trace['Knowledge activation'].state == expected
    if status == 'CLOSED':
        assert trace['Documentation PR'].state == 'Closed'


def test_other_repository_case_and_release_are_rejected():
    record = item()
    record['case'].repo_id = 'other'
    with pytest.raises(ValueError, match='another repository'):
        steps(record)
    record = item(release_status='INDEXED')
    record['release'].repo_id = 'other'
    with pytest.raises(ValueError, match='another review or repository'):
        steps(record)


def test_loader_scopes_versions_events_and_knowledge_to_case_repository(system):
    settings, engine, factory, repo_id = system
    with factory() as session:
        case, section, proposal, version = make_case(session, repo_id, accepted=True)
        other = Repository(full_name='owner/other', monitored_branch='main')
        session.add(other)
        session.flush()
        foreign_case, _, _, foreign_version = make_case(session, other.id, accepted=True)
        session.add(AuditEvent(case_id=foreign_case.id, kind='knowledge_index_activated',
            payload={'version_id': 'foreign', 'merged_sha': 'd' * 40}))
        session.add(KnowledgeVersion(id='foreign', repo_id=other.id, source_commit='d' * 40))
        session.commit()
        record = {'case': case, 'sections': [section], 'proposals': [proposal], 'release': None}
        # A corrupt accepted pointer cannot borrow a foreign proposal's version.
        proposal.accepted_version_id = foreign_version.id
        session.commit()
        repo = session.get(Repository, repo_id)
        knowledge = session.get(KnowledgeVersion, 'foreign')
    ctx = NS(repo_id=repo_id, factory=factory)
    view = {'repo': repo, 'versions': [knowledge], 'version_names': {'foreign': 'K99'}}
    trace = {s.title: s for s in load_change_trace(ctx, record, view)}
    assert trace['Human approval'].state == 'Pending'
    assert trace['Knowledge activation'].state == 'Not verified'
    assert all('K99' not in detail for step in trace.values() for detail in step.details)
