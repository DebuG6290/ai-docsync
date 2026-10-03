"""Small, explicit setup steps over the existing repository lifecycle."""
import re

import streamlit as st
from docsync.ui.components import heading, action, prose
from docsync.online.onboarding import (verify_access, connect_repository, discover, mapping_suggestions,
    confirm_mapping, workflow_files, release_sha)
from docsync.sarvam import SarvamClient
from docsync.web.github import GitHubError
from docsync.web.workflow import approved_mappings


def reset_suggestions():
    for key in list(st.session_state):
        if key in {'mapping_suggestions', 'ignored_mappings'} or key.startswith(('mapping-target-', 'mapping-reason-')):
            st.session_state.pop(key, None)


def parse_bulk_selection(raw, options):
    """Parse newline/comma separated values into matched and unmatched options."""
    option_set = set(options)
    matched = []
    unmatched = []
    seen = set()
    for value in re.split(r'[\n,]+', raw or ''):
        value = value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        if value in option_set:
            matched.append(value)
        else:
            unmatched.append(value)
    return matched, unmatched


def bulk_multiselect(label, options, *, key, default=None):
    """Multiselect with a paste-once helper for long exact option identifiers."""
    # A repository switch or a new discovery commit can invalidate old widget values.
    if key in st.session_state:
        st.session_state[key] = [value for value in st.session_state[key] if value in options]

    paste_key = key + '-paste'
    unmatched_key = key + '-unmatched'
    with st.expander('Paste ' + label.lower() + ' list'):
        st.caption('Paste one exact value per line, or a comma-separated list, then apply it once.')
        raw = st.text_area('Paste values', key=paste_key, label_visibility='collapsed',
            placeholder='value-one\nvalue-two')
        if st.button('Apply pasted list', key=key + '-apply'):
            matched, unmatched = parse_bulk_selection(raw, options)
            st.session_state[key] = matched
            st.session_state[unmatched_key] = unmatched
            st.rerun()
        unmatched = st.session_state.get(unmatched_key, [])
        if unmatched:
            st.warning('Not found: ' + ', '.join(unmatched))
        elif st.session_state.get(key) and raw:
            st.caption(f"{len(st.session_state[key])} pasted values matched.")

    widget_args = {'key': key}
    if key not in st.session_state:
        widget_args['default'] = default or []
    return st.multiselect(label, options, **widget_args)


def connect(settings, factory):
    heading('Connect repository', 'Add a repository to this workspace. Knowledge requires a separate approved baseline.', 'REPOSITORY SETUP')
    st.caption('Install or authorize the configured GitHub App on this repository first. Its installation ID can differ from HTTPX.')
    with st.form('connect-repository'):
        name = st.text_input('Repository', placeholder='owner/repo')
        branch = st.text_input('Monitored branch', value='main')
        installation = st.number_input('GitHub App installation ID', min_value=1, step=1,
            help='Find the ID in the installation settings URL. This is an identifier, not a credential.')
        submitted = st.form_submit_button('Verify GitHub App access', type='primary')
    if submitted:
        st.session_state.pop('verified_repository', None)
        try:
            with st.spinner('Checking App permissions, repository access and branch…'):
                st.session_state.verified_repository = verify_access(settings, name, branch, int(installation))
        except (GitHubError, ValueError):
            st.error('Access could not be verified. Install/authorize the configured GitHub App on this repository, check its installation ID and branch, and keep the existing contents/pull requests write permissions. No PAT is needed.')
    verified = st.session_state.get('verified_repository')
    if verified:
        st.success(f"Access verified: {verified['name']} · {verified['branch']}")
        st.caption('Discovery commit: ' + verified['sha'])
        if st.button('Connect verified repository', type='primary'):
            with factory() as session:
                repo = connect_repository(session, verified)
            # Apply selection on the next run, before sidebar widget construction.
            st.session_state.connected_repository_id = repo.id
            st.rerun()
    if st.button('Back to workspace'):
        st.session_state.pop('connecting', None)
        st.rerun()


def setup(ctx, view):
    stage = st.radio('Repository setup', ['Documentation', 'Mappings', 'Integration', 'Baseline'], horizontal=True, key='setup-stage')
    snapshot = st.session_state.get('discovery')
    if snapshot and snapshot['repo_id'] != ctx.repo_id:
        snapshot = None
    if stage == 'Documentation':
        st.subheader('Discover documentation and code')
        st.caption('DocSync currently analyzes Python symbols and Markdown sections. Discovery reads a fixed commit without running repository code.')
        if st.button('Discover repository structure'):
            try:
                with st.spinner('Reading repository paths…'):
                    st.session_state.discovery = discover(ctx.settings, view['repo'])
                reset_suggestions()
                st.rerun()
            except (GitHubError, ValueError):
                st.error('Discovery failed. Check GitHub App access and the monitored branch.')
        if snapshot:
            st.caption('Inspected commit: ' + snapshot['sha'])
            docs = [p for p in snapshot['files'] if p.endswith('.md')]
            code = [p for p in snapshot['files'] if p.endswith('.py')]
            st.write(f'{len(docs)} Markdown files · {len(code)} Python files')
            doc_paths = bulk_multiselect('Documentation files', docs,
                key=f'documentation-files-{ctx.repo_id}',
                default=[p for p in docs if p.startswith('docs/')][:5])
            code_paths = bulk_multiselect('Python files', code,
                key=f'python-files-{ctx.repo_id}')
            if st.button('Inspect selected files', type='primary'):
                try:
                    with st.spinner('Parsing selected code and documentation…'):
                        st.session_state.discovery = discover(ctx.settings, view['repo'], code_paths=code_paths,
                            doc_paths=doc_paths, commit=snapshot['sha'])
                    reset_suggestions()
                    st.rerun()
                except (GitHubError, ValueError) as exc:
                    st.error(str(exc))
            if snapshot['skipped']:
                st.warning('Unsupported Python syntax in: ' + ', '.join(snapshot['skipped']))
            if snapshot['sections']:
                st.write(f"{len(snapshot['symbols'])} symbols · {len(snapshot['sections'])} documentation sections inspected")
                with st.expander('Documentation sections'):
                    for section in snapshot['sections']:
                        st.write(section['section_id'])
                        prose(section['text'])
                st.caption('Continue to Mappings to confirm relationships. Inspected content is not approved knowledge.')
    elif stage == 'Mappings':
        st.subheader('Confirm code-to-documentation relationships')
        if not snapshot or not snapshot['symbols'] or not snapshot['sections']:
            st.info('Inspect Python files and Markdown documentation in the Documentation step first. New repositories have no approved mappings.')
            return
        symbols = {s['code_id']: s for s in snapshot['symbols']}
        sections = {s['section_id']: s for s in snapshot['sections']}
        selected_code = bulk_multiselect('Symbols for suggestions', list(symbols),
            key=f'mapping-symbols-{ctx.repo_id}', default=list(symbols)[:10])
        selected_sections = bulk_multiselect('Documentation for suggestions', list(sections),
            key=f'mapping-sections-{ctx.repo_id}', default=list(sections)[:10])
        st.caption('Suggestions use Sarvam and require human confirmation. Select a small batch; manual mappings need no model call.')
        if st.button('Suggest relationships with Sarvam'):
            try:
                with st.spinner('Suggesting candidate relationships…'):
                    scoped = {**snapshot, 'symbols': [symbols[k] for k in selected_code], 'sections': [sections[k] for k in selected_sections]}
                    with ctx.factory() as session:
                        suggestions = mapping_suggestions(session, ctx.repo_id, scoped, SarvamClient(ctx.settings.sarvam_model))
                    reset_suggestions()
                    st.session_state.mapping_suggestions = suggestions
                st.rerun()
            except Exception:
                st.error('Suggestions could not finish. Keep the batch within 30 symbols and 30 sections, check operation diagnostics, or confirm a manual relationship.')
        suggestions = st.session_state.get('mapping_suggestions', [])
        with ctx.factory() as session:
            confirmed = {(m['code_id'], m['section_id']) for m in approved_mappings(session, ctx.repo_id)}
        for index, suggestion in enumerate(suggestions):
            if (suggestion['code_id'], suggestion['section_id']) in confirmed or index in st.session_state.get('ignored_mappings', []):
                continue
            with st.container(border=True):
                st.write(suggestion['code_id'])
                target = st.selectbox('Suggested documentation / choose another section', list(sections),
                    index=list(sections).index(suggestion['section_id']), key=f'mapping-target-{index}')
                prose(suggestion['reason'])
                reason = st.text_input('Confirmation reason', value=suggestion['reason'], key=f'mapping-reason-{index}')
                approve, ignore = st.columns(2)
                if approve.button('Confirm mapping', key=f'confirm-mapping-{index}', type='primary'):
                    def save(s=suggestion, target=target, reason=reason):
                        with ctx.factory() as session:
                            confirm_mapping(session, ctx.repo_id, snapshot, s['code_id'], target, reason)
                    action(save, 'Mapping confirmed for this repository.')
                if ignore.button('Ignore', key=f'ignore-mapping-{index}'):
                    st.session_state.ignored_mappings = [*st.session_state.get('ignored_mappings', []), index]
                    st.rerun()
        with st.expander('Create a manual mapping'):
            with st.form('manual-mapping'):
                code_id = st.selectbox('Code symbol', list(symbols))
                section_id = st.selectbox('Documentation section', list(sections))
                reason = st.text_input('Why does this section document this symbol?')
                if st.form_submit_button('Confirm manual mapping', type='primary'):
                    def save_manual():
                        with ctx.factory() as session:
                            confirm_mapping(session, ctx.repo_id, snapshot, code_id, section_id, reason)
                    action(save_manual, 'Mapping confirmed for this repository.')
        st.caption(f'{len(confirmed)} approved mappings. Confirmation does not approve the documentation baseline.')
    elif stage == 'Integration':
        st.subheader('Install the two caller workflows')
        st.caption('Add these files through a reviewed commit or PR in the selected repository. DocSync does not push setup files automatically.')
        try:
            release = release_sha()
            st.caption('Application release SHA: ' + release)
            for path, content in workflow_files(view['repo'].monitored_branch, release).items():
                with st.expander(path):
                    st.code(content, language='yaml')
                    st.download_button('Download ' + path.split('/')[-1], content, file_name=path.split('/')[-1], mime='text/yaml')
            st.write('Set DATABASE_URL to this workspace database in the repository Actions secrets. Add SARVAM_API_KEY for analysis. Actions uses its built-in read-only GITHUB_TOKEN; keep App credentials in Streamlit.')
            st.caption('Enable Actions and reusable workflows. Merge the callers before running the baseline step.')
        except Exception:
            st.error('The application release SHA is unavailable. Use the full reviewed application commit SHA for both workflow and application_ref pins; see DEPLOYMENT.md.')
    else:
        st.subheader('Initialize approved knowledge')
        if view['active']:
            st.success('Approved knowledge is active for this repository.')
            st.caption('Source commit: ' + view['active'].source_commit)
        else:
            st.info('Repository connected ≠ approved knowledge initialized. Chat stays unavailable until indexing activates a verified baseline.')
            st.write('Review the documentation at a full source commit. Then explicitly approve it by running DocSync index → Run workflow with that 40-character baseline_sha. This is a human approval action.')
            st.caption('The baseline includes Markdown under docs/ and documentation files referenced by approved mappings. It never uses the branch tip implicitly and cannot replace an existing active version.')
            st.link_button('Open baseline indexing workflow', f'https://github.com/{view["repo"].full_name}/actions/workflows/docsync-index.yml')
            st.caption('Wait for a successful Action, refresh this workspace and check Knowledge before using Chat.')
