"""Public sample surface. Never imports production configuration or credentials."""
import streamlit as st

from docsync.demo import BEFORE, create_demo
from docsync.ui.components import heading, styles
from docsync.ui.reviews import show_diff


def main():
    st.set_page_config(page_title='Try DocSync', page_icon='D', layout='wide')
    styles()
    if 'demo_workspace' not in st.session_state:
        st.session_state.demo_workspace = create_demo()
    workspace = st.session_state.demo_workspace
    snapshot = workspace.snapshot()
    with st.sidebar:
        st.title('DocSync')
        st.caption('From code changes to trusted answers.')
        st.info('Isolated sample · no account or API key')
        st.write('1. Inspect the change\n2. Review and approve\n3. Simulate a merge\n4. Check approved knowledge')
        st.link_button('Set up your own workspace', 'https://github.com/DebuG6290/ai-docsync#readme')
        if st.button('Reset sample'):
            workspace.engine.dispose()
            st.session_state.clear()
            st.rerun()
    heading('See what happens when the code changes.', 'A developer changes the default timeout from five to eight seconds. You decide what becomes trusted knowledge.', 'TRY DOCSYNC')
    st.caption('Suggestions and merge events are scripted. Approval, immutable versions and knowledge activation use the actual DocSync services. No network requests are made.')
    left, right = st.columns([3, 2], gap='large')
    with left:
        st.subheader('1. A code change needs a documentation review')
        st.code('- DEFAULT_TIMEOUT = 5\n+ DEFAULT_TIMEOUT = 8', language='diff')
        st.subheader('2. Review the proposed update')
        st.caption('Sample suggestion · version ' + str(snapshot['latest'].version))
        show_diff(BEFORE, snapshot['latest'].proposed_text)
        accepted = snapshot['proposal'].status == 'ACCEPTED'
        if accepted:
            st.success('This exact version is approved. Chat still uses the previous snapshot until activation.')
        else:
            with st.expander('Edit before approving'):
                with st.form('demo-edit'):
                    content = st.text_area('Documentation text', value=snapshot['latest'].proposed_text, max_chars=100000)
                    if st.form_submit_button('Save edit'):
                        try:
                            workspace.save_edit(content)
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
            if st.button('Approve this version', type='primary'):
                workspace.approve()
                st.rerun()
        st.subheader('3. Publish through a reviewed merge')
        st.write('In a connected workspace, DocSync creates a docs-only PR and verifies its merge before activating knowledge.')
        if st.button('Simulate merge and activate knowledge', disabled=not accepted or snapshot['activated']):
            workspace.simulate_merge()
            st.rerun()
        if snapshot['activated']:
            st.success('The approved sample documentation is now active.')
    with right:
        with st.container(border=True):
            st.subheader('4. What does Chat know right now?')
            st.caption('Approved source excerpt · this sample uses direct retrieval, with no LLM answer generation.')
            st.markdown(snapshot['approved_text'])
            st.caption('Source: docs/client.md · version ' + snapshot['version'].id[:8])
            if not snapshot['activated']:
                st.info('Pending suggestions do not enter approved knowledge.')
            st.download_button('Download approved documentation', snapshot['approved_text'],
                file_name='client.md', mime='text/markdown')
        with st.expander('Inspect the audit trail'):
            for event in snapshot['events']:
                st.write(event.kind.replace('_', ' ').capitalize())
                st.json(event.payload)


if __name__ == '__main__':
    main()
