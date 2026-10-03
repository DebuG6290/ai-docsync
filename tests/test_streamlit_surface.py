from streamlit.testing.v1 import AppTest
from pathlib import Path
from test_online_phase2 import system
from test_online_phase2 import make_case
from docsync.web.models import Proposal, ProposalVersion


def test_streamlit_login_and_authenticated_status(system, monkeypatch):
    settings, engine, factory, repo_id = system
    values = {'DATABASE_URL': settings.database_url, 'DOCSYNC_REPOSITORY': settings.repository,
        'DOCSYNC_REVIEW_USERNAME': 'reviewer', 'DOCSYNC_REVIEW_PASSWORD': 'test-long-password',
        'DOCSYNC_HOSTED': 'false', 'SARVAM_API_KEY': 'test-key'}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'streamlit_app.py')
    app.secrets.update(values)
    app.run(timeout=20)
    assert not app.exception
    assert len(app.text_input) == 2
    app.text_input[0].set_value('reviewer')
    app.text_input[1].set_value('test-long-password')
    app.button[0].click().run(timeout=20)
    assert not app.exception
    app.sidebar.radio[0].set_value('Settings').run(timeout=20)
    assert not app.exception
    assert not app.error
    assert any(settings.repository in m.value for m in app.markdown)

    for page in ['Home', 'Reviews', 'Knowledge', 'Chat', 'History']:
        app.sidebar.radio[0].set_value(page).run(timeout=20)
        assert not app.exception
        assert not app.error


def test_human_edit_survives_navigation_and_requires_separate_approval(system, monkeypatch):
    settings, engine, factory, repo_id = system
    with factory() as session:
        case, section, proposal, version = make_case(session, repo_id)
        session.commit()
        proposal_id = proposal.id
    values = {'DATABASE_URL': settings.database_url, 'DOCSYNC_REPOSITORY': settings.repository,
        'DOCSYNC_REVIEW_USERNAME': 'reviewer', 'DOCSYNC_REVIEW_PASSWORD': 'test-long-password',
        'DOCSYNC_HOSTED': 'false', 'SARVAM_API_KEY': 'test-key'}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'streamlit_app.py')
    app.secrets.update(values)
    app.run(timeout=20)
    app.text_input[0].set_value('reviewer')
    app.text_input[1].set_value('test-long-password')
    app.button[0].click().run(timeout=20)
    app.sidebar.radio[0].set_value('Reviews').run(timeout=20)
    next(b for b in app.button if b.label == 'Open review').click().run(timeout=20)
    next(b for b in app.button if b.label == 'Edit suggestion').click().run(timeout=20)
    text = '## Default timeout\nHuman-approved wording: eight seconds.\n'
    next(t for t in app.text_area if t.label == 'Documentation text').set_value(text).run(timeout=20)
    app.sidebar.radio[0].set_value('Knowledge').run(timeout=20)
    app.sidebar.radio[0].set_value('Reviews').run(timeout=20)
    assert next(t for t in app.text_area if t.label == 'Documentation text').value == text
    next(b for b in app.button if b.label == 'Save edit').click().run(timeout=20)
    assert not app.exception and not app.error
    with factory() as session:
        proposal = session.get(Proposal, proposal_id)
        assert proposal.status == 'PENDING'
        assert not proposal.accepted_version_id
    next(b for b in app.button if b.label == 'Approve update').click().run(timeout=20)
    assert not app.exception and not app.error
    with factory() as session:
        proposal = session.get(Proposal, proposal_id)
        approved = session.get(ProposalVersion, proposal.accepted_version_id)
        assert approved.proposed_text == text
        assert approved.author == 'human'
