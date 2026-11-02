from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from docsync.demo import create_demo, BEFORE, AFTER


def test_offline_sample_uses_approval_and_isolated_knowledge(monkeypatch):
    monkeypatch.setattr('socket.create_connection', lambda *a, **k: pytest.fail('The sample must work offline'))
    first, other = create_demo(), create_demo()
    assert first.snapshot()['approved_text'] == BEFORE
    with pytest.raises(ValueError, match='Approve'):
        first.simulate_merge()
    custom = '## Default timeout\nThe reviewed sample timeout is eight seconds.\n'
    first.save_edit(custom)
    assert first.snapshot()['latest'].version == 2
    assert first.snapshot()['approved_text'] == BEFORE
    first.approve()
    assert first.snapshot()['approved_text'] == BEFORE
    first.simulate_merge()
    assert first.snapshot()['approved_text'] == custom
    assert other.snapshot()['approved_text'] == BEFORE
    with pytest.raises(ValueError, match='already activated'):
        first.simulate_merge()
    assert any(e.payload.get('actor_id') == 'local:sample-reviewer' for e in first.snapshot()['events'])
    first.engine.dispose()
    other.engine.dispose()


def test_sample_ui_completes_without_credentials_or_network(monkeypatch):
    monkeypatch.setattr('socket.create_connection', lambda *a, **k: pytest.fail('No sample network requests'))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'demo_app.py').run(timeout=20)
    assert not app.exception and not app.error
    assert next(b for b in app.button if b.label == 'Simulate merge and activate knowledge').disabled
    next(b for b in app.button if b.label == 'Approve this version').click().run(timeout=20)
    assert app.session_state['demo_workspace'].snapshot()['approved_text'] == BEFORE
    next(b for b in app.button if b.label == 'Simulate merge and activate knowledge').click().run(timeout=20)
    assert not app.exception and not app.error
    assert app.session_state['demo_workspace'].snapshot()['approved_text'] == AFTER
    next(b for b in app.button if b.label == 'Reset sample').click().run(timeout=20)
    assert not app.exception and not app.error
    assert app.session_state['demo_workspace'].snapshot()['approved_text'] == BEFORE
