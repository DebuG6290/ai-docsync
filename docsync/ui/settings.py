import streamlit as st
from docsync.ui.components import heading
from docsync.web.workflow import approved_mappings


def render(ctx, view):
    heading('Workspace settings', 'Repository configuration and approved mapping details.', 'CONFIGURATION')
    st.markdown('### Monitored repository')
    st.write(ctx.settings.repository)
    st.caption('Branch: ' + ctx.settings.monitored_branch)
    st.link_button('Open repository', 'https://github.com/' + ctx.settings.repository)
    with st.expander('Approved code-to-documentation mappings'):
        with ctx.factory() as session:
            mappings = approved_mappings(session, ctx.repo_id)
        st.dataframe(mappings, hide_index=True, use_container_width=True)
        st.caption('Mappings select candidate sections. The model assesses documentation impact.')
    with st.expander('Runtime details'):
        st.write('Reasoning model: ' + ctx.settings.sarvam_model)
        st.write('Local embedding model: ' + ctx.settings.embedding_model)
        st.caption('GitHub Actions · Neon PostgreSQL / pgvector · Streamlit Community Cloud')
        st.caption('Credentials are managed through deployment secrets and are never displayed here.')
