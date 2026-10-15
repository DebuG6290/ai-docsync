from types import SimpleNamespace
import inspect

import pytest
from streamlit.testing.v1 import AppTest

from docsync.ui.reviews import displayed_version


def evidence_app():
    from types import SimpleNamespace
    from docsync.ui.reviews import inspect_evidence

    section = SimpleNamespace(evidence_completeness='COMPLETE', code_evidence=['original code'],
        missing_information=['original dependency gap'], safe_claims=['original claim'],
        unsupported_claims=['original unestablished claim'], decision='UPDATE',
        section_id='docs/guide.md::example', triage_reason=None, base_sha256='original-hash')
    case = SimpleNamespace(before_sha='a'*40, after_sha='b'*40, case_data={})
    kind = __import__('streamlit').session_state.get('kind', 'revised')
    version = SimpleNamespace(version=2, author='human' if kind == 'human' else 'sarvam',
        evidence_completeness=None if kind in {'human', 'legacy'} else 'PARTIAL',
        code_evidence=[] if kind == 'human' else ['revised code'],
        missing_information=[] if kind == 'human' else ['revised dependency gap'],
        safe_claims=[] if kind == 'human' else ['revised claim'],
        unsupported_claims=[] if kind == 'human' else ['revised unestablished claim'])
    inspect_evidence(case, section, version)


def text_in(container):
    return '\n'.join(x.value for x in [*container.markdown, *container.caption])


@pytest.fixture
def evidence_surface(tmp_path):
    script = tmp_path / 'evidence_app.py'
    script.write_text(inspect.getsource(evidence_app) + '\nevidence_app()\n', encoding='utf-8')
    return AppTest.from_file(script)


def test_revised_evidence_is_version_bound_and_initial_assessment_is_separate(evidence_surface):
    app = evidence_surface.run()
    assert not app.exception
    shown = text_in(app.expander[0])
    original = text_in(app.expander[1])
    assert 'revised code' in shown and 'revised claim' in shown and 'Partial' in shown
    assert 'original code' not in shown and 'original claim' not in shown
    assert 'original code' in original and 'original claim' in original
    assert 'Model-assessed claims' in shown and 'not independent human factual-support labels' in shown


@pytest.mark.parametrize('kind', ['human', 'legacy'])
def test_missing_version_metadata_never_falls_back_to_initial_assessment(kind, evidence_surface):
    app = evidence_surface
    app.session_state['kind'] = kind
    app.run()
    assert not app.exception
    shown = text_in(app.expander[0])
    assert 'Not recorded' in shown and 'original claim' not in shown
    if kind == 'human':
        assert 'Human-authored version' in shown and 'original dependency gap' not in shown


def test_approved_text_and_evidence_use_accepted_version_even_if_newer_row_exists():
    accepted = SimpleNamespace(id='approved')
    newer = SimpleNamespace(id='newer')
    assert displayed_version(SimpleNamespace(status='ACCEPTED', accepted_version_id='approved'), [accepted, newer]) is accepted
    assert displayed_version(SimpleNamespace(status='PENDING'), [accepted, newer]) is newer
    with pytest.raises(ValueError, match='approved proposal version is unavailable'):
        displayed_version(SimpleNamespace(status='APPLIED', accepted_version_id='missing'), [newer])
