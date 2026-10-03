"""Mechanical publication-context validation; never infer semantic impact."""
from docsync.errors import ConflictError
from docsync.repository.markdown_sections import parse_sections, section_sha256


def validate_drift(root, git, case, assessments, tip):
    base = case.after_sha
    data = {'reviewed_base_sha': base, 'validated_current_tip': tip,
        'publication_parent_sha': tip, 'intervening_commit_count': 0, 'intervening_file_count': 0,
        'overlapping_reviewed_code_files': [], 'overlapping_reviewed_doc_sections': []}

    def block(result, message):
        error = ConflictError(message)
        error.publication_drift = {**data, 'validation_result': result}
        raise error

    expected = {s['section_id'] for s in case.case_data.get('sections', [])}
    observed = [a.section_id for a in assessments]
    if not expected or set(observed) != expected or len(observed) != len(expected):
        block('MISSING_DOCUMENTATION_CONTEXT', 'Reviewed documentation context is incomplete. A fresh review is required before publishing.')

    if tip != base:
        try:
            ancestor = git('merge-base', base, tip)
        except RuntimeError:
            ancestor = None
        if ancestor != base:
            block('DIVERGED', 'Repository history diverged from this review. Start a fresh review before publishing.')
        data['intervening_commit_count'] = int(git('rev-list', '--count', f'{base}..{tip}'))
        # Include every intervening commit, including reverted edits and merge diffs.
        changed = {p.strip('\n') for p in git('log', '--format=', '--name-only', '-z',
            '--no-renames', '--diff-merges=first-parent', f'{base}..{tip}').split('\0') if p.strip('\n')}
        data['intervening_file_count'] = len(changed)
        reviewed = {c['path'] for c in case.case_data.get('changes', []) if c.get('path')}
        reviewed.update(m['code_id'].partition('::')[0] for m in case.case_data.get('mappings', []) if m.get('code_id'))
        if not reviewed:
            block('MISSING_CODE_CONTEXT', 'Reviewed code context is unavailable. A fresh analysis is required before publishing.')
        data['overlapping_reviewed_code_files'] = sorted(changed & reviewed)
        if data['overlapping_reviewed_code_files']:
            block('CODE_DRIFT', 'Reviewed code changed again before publication. A new analysis is required.')
    for assessment in assessments:
        path = (root / assessment.path).resolve()
        try:
            path.relative_to(root.resolve())
            with path.open(encoding='utf-8', newline='') as stream:
                text = stream.read()
            section = next((s for s in parse_sections(assessment.path, text)
                if s.section_id == assessment.section_id), None)
            matches = (section is not None and section_sha256(assessment.current_text) == assessment.base_sha256
                and section_sha256(section.text) == assessment.base_sha256)
        except (OSError, ValueError, UnicodeError):
            matches = False
        if not matches:
            data['overlapping_reviewed_doc_sections'].append(assessment.section_id)
    if data['overlapping_reviewed_doc_sections']:
        block('DOCUMENTATION_DRIFT', 'Documentation changed since this review. Start a fresh review before publishing.')
    return {**data, 'validation_result': 'SAFE_UNRELATED_ADVANCE' if tip != base else 'UNCHANGED'}
