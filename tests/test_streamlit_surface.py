from streamlit.testing.v1 import AppTest
from pathlib import Path
from test_online_phase2 import system


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
    app.sidebar.radio[0].set_value('Settings / Status').run(timeout=20)
    assert not app.exception
    assert settings.repository in app.json[0].value
