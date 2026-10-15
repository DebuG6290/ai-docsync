"""Deterministic mapping coverage; no documentation-impact inference."""


def _approved_pairs(mappings, repo_id=None):
    pairs = set()
    for mapping in mappings:
        if repo_id is not None and mapping.get('repo_id', repo_id) != repo_id:
            raise ValueError('Mapping belongs to another repository')
        if mapping.get('status', 'APPROVED') != 'APPROVED':
            continue
        if mapping.get('code_id') and mapping.get('section_id'):
            pairs.add((mapping['code_id'], mapping['section_id']))
    return pairs


def changed_symbol_coverage(case_data):
    """Describe the saved analysis scope without assigning semantic decisions."""
    changes = case_data.get('changes', [])
    changed = {change['code_id'] for change in changes if change.get('code_id')}
    mapped = changed & {code_id for code_id, _ in _approved_pairs(case_data.get('mappings', []))}
    deleted = {change['code_id'] for change in changes
        if change.get('code_id') and change.get('change_kind') == 'deleted'}
    return {'changed_code_ids': sorted(changed), 'mapped_code_ids': sorted(mapped),
        'unmapped_code_ids': sorted(changed - mapped), 'deleted_code_ids': sorted(deleted)}


def snapshot_mapping_health(snapshot, mappings, repo_id):
    """Validate identities only in successfully inspected files at the saved SHA.

    Repository paths alone do not establish inspected content. Legacy snapshots
    can establish scope only for files with parsed symbols or sections.
    """
    if snapshot.get('repo_id') != repo_id:
        raise ValueError('Discovery belongs to another repository')
    pairs = _approved_pairs(mappings, repo_id)
    symbols = {item['code_id'] for item in snapshot.get('symbols', [])}
    sections = {item['section_id'] for item in snapshot.get('sections', [])}
    skipped = set(snapshot.get('skipped', []))
    code_paths = set(snapshot.get('inspected_code_paths',
        [item.get('path') or item['code_id'].partition('::')[0] for item in snapshot.get('symbols', [])])) - skipped
    doc_paths = set(snapshot.get('inspected_doc_paths',
        [item.get('path') or item['section_id'].partition('::')[0] for item in snapshot.get('sections', [])]))
    missing_code = set()
    missing_sections = set()
    unchecked = 0
    for code_id, section_id in pairs:
        code_path = code_id.partition('::')[0]
        doc_path = section_id.partition('::')[0]
        if code_path in code_paths and code_id not in symbols:
            missing_code.add(code_id)
        if doc_path in doc_paths and section_id not in sections:
            missing_sections.add(section_id)
        if code_path not in code_paths or doc_path not in doc_paths:
            unchecked += 1
    inspected_symbols = {symbol for symbol in symbols if symbol.partition('::')[0] in code_paths}
    mapped_symbols = {code_id for code_id, _ in pairs}
    return {'unmapped_code_ids': sorted(inspected_symbols - mapped_symbols),
        'missing_code_ids': sorted(missing_code), 'missing_section_ids': sorted(missing_sections),
        'unchecked_mapping_count': unchecked, 'inspected_code_paths': sorted(code_paths),
        'inspected_doc_paths': sorted(doc_paths), 'skipped_code_paths': sorted(skipped)}


def render_snapshot_health(snapshot, mappings, repo_id):
    import streamlit as st

    health = snapshot_mapping_health(snapshot, mappings, repo_id)
    issues = any(health[key] for key in ('unmapped_code_ids', 'missing_code_ids', 'missing_section_ids'))
    with st.expander('Mapping health for inspected files', expanded=issues):
        st.caption('Checked only successfully inspected files at commit ' + snapshot['sha'] + '.')
        for key, message in [
            ('unmapped_code_ids', 'Inspected symbols without an approved mapping. Changes to these symbols are not assessed through approved mappings.'),
            ('missing_code_ids', 'Mapped symbols missing from the inspected Python files.'),
            ('missing_section_ids', 'Mapped documentation sections missing from the inspected Markdown files.'),
        ]:
            if health[key]:
                st.warning(message)
                st.code('\n'.join(health[key]), language=None)
        if not health['inspected_code_paths'] and not health['inspected_doc_paths']:
            st.info('Inspect selected files in Documentation to check mapping identities.')
        elif not issues:
            st.caption('No missing mapping identities were found within the inspected files.')
        if health['unchecked_mapping_count']:
            st.caption(f"{health['unchecked_mapping_count']} approved relationships have an endpoint outside this inspection and remain unchecked.")
        if health['skipped_code_paths']:
            st.caption('Python files with unsupported syntax remain unchecked: ' + ', '.join(health['skipped_code_paths']))
        st.caption('Use Create a manual mapping below for missing relationships. Mappings select candidates; they do not determine impact or approve knowledge.')
    return health
