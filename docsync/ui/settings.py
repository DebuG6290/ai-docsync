import streamlit as st
from docsync.ui.components import heading
from docsync.web.workflow import approved_mappings
from docsync.ui.onboarding import setup
from docsync.online.onboarding import verify_access


def render(ctx, view):
    heading('Workspace settings', 'Repository configuration and approved mapping details.', 'CONFIGURATION')
    st.markdown('### Monitored repository')
    st.write(ctx.settings.repository)
    st.caption('Branch: ' + ctx.settings.monitored_branch)
    st.link_button('Open repository', 'https://github.com/' + ctx.settings.repository)
    with ctx.factory() as session:
        mappings = approved_mappings(session, ctx.repo_id)
    st.write(f'{len(mappings)} approved mappings')
    st.write('Active knowledge: ' + (view['version_names'][view['active'].id] if view['active'] else 'Not initialized'))
    st.caption('GitHub App installation recorded' if view['repo'].installation_id else 'GitHub App installation needs validation')
    if st.button('Check GitHub App access'):
        try:
            verify_access(ctx.settings, view['repo'].full_name, view['repo'].monitored_branch, view['repo'].installation_id or 0)
            st.success('GitHub App read/write access and monitored branch verified.')
        except Exception:
            st.error('Access could not be verified. Check the App installation and branch. Saved repository configuration is unchanged.')
    with st.expander('Approved code-to-documentation mappings'):
        st.dataframe(mappings, hide_index=True, use_container_width=True)
        st.caption('Mappings select candidate sections. The model assesses documentation impact.')
    with st.expander('Runtime details'):
        st.write('Reasoning model: ' + ctx.settings.sarvam_model)
        st.write('Local embedding model: ' + ctx.settings.embedding_model)
        st.caption('GitHub Actions · Neon PostgreSQL / pgvector · Streamlit Community Cloud')
        st.caption('Credentials are managed through deployment secrets and are never displayed here.')
    st.divider()
    setup(ctx, view)
