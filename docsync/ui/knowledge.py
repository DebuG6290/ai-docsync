import streamlit as st
from sqlalchemy import select
from docsync.ui.components import heading, badge, empty, short, date, action
from docsync.ui.state import release_status
from docsync.online.status import reconcile_release
from docsync.web.models import IndexedSection


def render(ctx, view):
    heading('Approved knowledge', 'Follow each documentation update from GitHub merge to the version Chat can use.', 'KNOWLEDGE & RELEASES')
    from docsync.ui.conflicts import render as conflict_review
    conflict_review(ctx, view)
    active = view['active']
    if not active:
        empty('Start with approved documentation', 'Choose and explicitly approve a full source commit before asking Chat or analyzing code changes. Connection alone does not approve knowledge.')
        st.link_button('Open baseline indexing workflow', f'https://github.com/{ctx.settings.repository}/actions/workflows/docsync-index.yml', type='primary')
        if ctx.settings.repository.casefold() == 'debug6290/httpx':
            st.code('b5addb64f0161ff6bfe94c124ef76f6a1fba5254', language=None)
            st.caption('Original HTTPX demo baseline; use only for its first initialization.')
        st.caption('Run the index workflow with the reviewed 40-character baseline_sha. Existing knowledge cannot be replaced by baseline initialization.')
    else:
        with st.container(border=True):
            badge('Active · used by Chat', 'success')
            st.subheader(view['version_names'][active.id] + ' · Approved documentation')
            st.caption(f'Activated {date(active.created_at)} · snapshot {short(active.source_commit)}')
            st.link_button('View approved snapshot', f'https://github.com/{ctx.settings.repository}/tree/{active.source_commit}')
            with st.expander('Included documentation sections'):
                with ctx.factory() as session:
                    rows = session.scalars(select(IndexedSection).where(IndexedSection.version_id == active.id)
                        .order_by(IndexedSection.path, IndexedSection.section_id, IndexedSection.chunk_index)).all()
                seen = set()
                for row in rows:
                    if row.section_id in seen:
                        continue
                    seen.add(row.section_id)
                    st.write(f'{row.heading or "Introduction"} · {row.path}')
                    st.caption('Section provenance: ' + short(row.source_commit))
                st.caption('Unchanged sections retain their previous approved source commit.')
    st.subheader('Documentation updates')
    if not view['releases']:
        st.caption('Approved documentation PRs will appear here after review.')
    for release in sorted(view['releases'], key=lambda r: r.merged_at.timestamp() if r.merged_at else 0, reverse=True):
        status = release_status(release, view['jobs'])
        with st.container(border=True):
            badge(status.label, status.tone)
            st.markdown(f'### Documentation PR #{release.pr_number}' if release.pr_number else '### Approved publication snapshot')
            st.write(status.message)
            if release.merged_sha:
                st.caption(f'Merged commit {short(release.merged_sha)} · {date(release.merged_at)}')
            elif release.status_checked_at:
                st.caption('GitHub last checked ' + date(release.status_checked_at))
            else:
                st.caption('GitHub merge status has not been confirmed yet.')
            if release.pr_url:
                st.link_button('Open PR in GitHub', release.pr_url)
            if release.status != 'INDEXED' and release.pr_number:
                if st.button('Check GitHub status', key='check-' + release.id):
                    action(lambda: reconcile_release(ctx.factory, release.id, repo_id=ctx.repo_id), 'GitHub status checked.')
            if status.tone == 'error':
                st.link_button('Open indexing runs', f'https://github.com/{ctx.settings.repository}/actions/workflows/docsync-index.yml')
                st.caption('For execution failures, rerun the failed Action. For content conflicts, inspect the merged text before retrying.')
    with st.expander('Knowledge version history'):
        for version in reversed(view['versions']):
            st.write(f"{view['version_names'][version.id]} · {'Active' if version.id == view['repo'].active_index_version_id else 'Historical'} · {date(version.created_at)}")
            st.caption('Snapshot commit: ' + version.source_commit)
            st.caption('Knowledge identity: ' + version.id)
