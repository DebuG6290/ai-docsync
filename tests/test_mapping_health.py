from copy import deepcopy
from contextlib import nullcontext
from types import SimpleNamespace
import sys

import pytest

from docsync.ui.mapping_health import changed_symbol_coverage, snapshot_mapping_health, render_snapshot_health


def mapping(code_id='pkg/settings.py::DEFAULT', section_id='docs/settings.md::defaults', **extra):
    return {'code_id': code_id, 'section_id': section_id, **extra}


def snapshot(**extra):
    return {'repo_id': 'repo-a', 'sha': 'a' * 40,
        'files': ['pkg/settings.py', 'docs/settings.md', 'uninspected.py', 'uninspected.md'],
        'symbols': [{'code_id': 'pkg/settings.py::DEFAULT', 'path': 'pkg/settings.py'}],
        'sections': [{'section_id': 'docs/settings.md::defaults', 'path': 'docs/settings.md'}],
        'skipped': [], 'inspected_code_paths': ['pkg/settings.py'],
        'inspected_doc_paths': ['docs/settings.md'], **extra}


def test_partial_mapping_coverage_is_explicit_without_a_semantic_decision():
    case = {'changes': [
        {'code_id': 'pkg/settings.py::DEFAULT', 'change_kind': 'modified'},
        {'code_id': 'pkg/settings.py::OTHER', 'change_kind': 'added'},
        {'code_id': 'pkg/settings.py::OTHER', 'change_kind': 'added'},
    ], 'mappings': [mapping(), mapping(), mapping(code_id='pkg/settings.py::OTHER', status='PENDING')]}
    original = deepcopy(case)
    coverage = changed_symbol_coverage(case)
    assert coverage == {'changed_code_ids': ['pkg/settings.py::DEFAULT', 'pkg/settings.py::OTHER'],
        'mapped_code_ids': ['pkg/settings.py::DEFAULT'],
        'unmapped_code_ids': ['pkg/settings.py::OTHER'], 'deleted_code_ids': []}
    assert case == original
    assert 'decision' not in coverage


def test_deleted_mapped_symbol_remains_mapped_for_semantic_analysis():
    case = {'changes': [{'code_id': 'pkg/settings.py::DEFAULT', 'change_kind': 'deleted',
        'old_code': 'DEFAULT = 4', 'new_code': None}], 'mappings': [mapping()]}
    coverage = changed_symbol_coverage(case)
    assert coverage['mapped_code_ids'] == ['pkg/settings.py::DEFAULT']
    assert coverage['deleted_code_ids'] == ['pkg/settings.py::DEFAULT']
    assert coverage['unmapped_code_ids'] == []
    assert changed_symbol_coverage({})['changed_code_ids'] == []


def test_missing_mapped_symbol_and_heading_are_reported_only_in_inspected_files():
    inspected = snapshot()
    original = deepcopy(inspected)
    health = snapshot_mapping_health(inspected,
        [mapping('pkg/settings.py::REMOVED', 'docs/settings.md::removed')], 'repo-a')
    assert health['missing_code_ids'] == ['pkg/settings.py::REMOVED']
    assert health['missing_section_ids'] == ['docs/settings.md::removed']
    assert health['unmapped_code_ids'] == ['pkg/settings.py::DEFAULT']
    assert health['unchecked_mapping_count'] == 0
    assert inspected == original


def test_uninspected_repository_paths_are_not_treated_as_missing_identities():
    relationship = mapping('uninspected.py::function', 'uninspected.md::heading')
    health = snapshot_mapping_health(snapshot(), [mapping(), relationship, relationship], 'repo-a')
    assert health['missing_code_ids'] == []
    assert health['missing_section_ids'] == []
    assert health['unmapped_code_ids'] == []
    assert health['unchecked_mapping_count'] == 1


def test_successfully_inspected_empty_files_still_establish_scope():
    health = snapshot_mapping_health(snapshot(symbols=[], sections=[]), [mapping()], 'repo-a')
    assert health['missing_code_ids'] == ['pkg/settings.py::DEFAULT']
    assert health['missing_section_ids'] == ['docs/settings.md::defaults']


def test_unsupported_syntax_is_unchecked_instead_of_a_missing_symbol():
    health = snapshot_mapping_health(snapshot(symbols=[], skipped=['pkg/settings.py']), [mapping()], 'repo-a')
    assert health['missing_code_ids'] == []
    assert health['unchecked_mapping_count'] == 1
    assert health['skipped_code_paths'] == ['pkg/settings.py']


def test_legacy_snapshot_scope_comes_from_parsed_content_not_repository_file_list():
    inspected = snapshot()
    inspected.pop('inspected_code_paths')
    inspected.pop('inspected_doc_paths')
    health = snapshot_mapping_health(inspected,
        [mapping(), mapping('uninspected.py::function', 'uninspected.md::heading')], 'repo-a')
    assert health['missing_code_ids'] == []
    assert health['missing_section_ids'] == []
    assert health['unchecked_mapping_count'] == 1


def test_legacy_snapshot_can_use_stable_ids_without_explicit_path_fields():
    inspected = snapshot()
    inspected.pop('inspected_code_paths')
    inspected.pop('inspected_doc_paths')
    inspected['symbols'] = [{'code_id': 'pkg/settings.py::DEFAULT'}]
    inspected['sections'] = [{'section_id': 'docs/settings.md::defaults'}]
    health = snapshot_mapping_health(inspected, [mapping()], 'repo-a')
    assert health['missing_code_ids'] == []
    assert health['missing_section_ids'] == []
    assert health['unchecked_mapping_count'] == 0


@pytest.mark.parametrize('discovery,relationships', [
    (snapshot(repo_id='repo-b'), [mapping()]),
    (snapshot(), [mapping(repo_id='repo-b')]),
])
def test_health_rejects_foreign_repository_context(discovery, relationships):
    with pytest.raises(ValueError, match='another repository'):
        snapshot_mapping_health(discovery, relationships, 'repo-a')


def test_mapping_health_ui_explains_unassessed_scope_and_existing_manual_flow(monkeypatch):
    warnings, captions, identifiers = [], [], []
    surface = SimpleNamespace(expander=lambda *args, **kwargs: nullcontext(),
        warning=warnings.append, caption=captions.append, info=captions.append,
        code=lambda text, **kwargs: identifiers.append(text))
    monkeypatch.setitem(sys.modules, 'streamlit', surface)
    render_snapshot_health(snapshot(), [], 'repo-a')
    assert any('not assessed' in warning for warning in warnings)
    assert any('Create a manual mapping' in caption for caption in captions)
    assert identifiers == ['pkg/settings.py::DEFAULT']
