import streamlit as st
from sqlalchemy import select
from docsync.ui.components import heading, empty, date, short, action
from docsync.web.chat import answer_question, chat_history
from docsync.web.models import Repository, IndexedSection, KnowledgeVersion
from docsync.web.embeddings import SentenceEmbedder


@st.cache_resource
def embedder(model, directory):
    return SentenceEmbedder(model, directory)


def reask(question):
    st.session_state.reask = question


def render(ctx, view):
    heading('Ask your approved documentation', 'Answers come from approved documentation, with sources you can inspect.', 'DOCUMENTATION ASSISTANT')
    if not view['active']:
        empty('Chat needs an approved knowledge version', 'Initialize your baseline from Knowledge. Drafts and suggestions are never used as answers.')
        return
    with ctx.factory() as session:
        turns = chat_history(session, ctx.repo_id)
        rows = session.scalars(select(IndexedSection).join(KnowledgeVersion, IndexedSection.version_id == KnowledgeVersion.id)
            .where(KnowledgeVersion.repo_id == ctx.repo_id, IndexedSection.version_id.in_({t.knowledge_version_id for t in turns}))
            .order_by(IndexedSection.chunk_index)).all() if turns else []
    passages = {}
    for row in rows:
        key = (row.version_id, row.section_id)
        passages[key] = passages.get(key, '') + row.content
    if not turns:
        st.caption('Start with a question about the documentation. For example: “What is the default timeout?”')
    for turn in reversed(turns):
        with st.chat_message('user'):
            st.write(turn.question)
        with st.chat_message('assistant'):
            historical = turn.knowledge_version_id != view['active'].id
            version = view['version_names'].get(turn.knowledge_version_id, 'Earlier version')
            if historical:
                st.caption(f'Historical answer · {version} · {date(turn.created_at)}')
                st.info('Answered using an earlier approved knowledge version. Its original sources are preserved.')
            else:
                st.caption(f"Uses current approved knowledge · {version} · {date(turn.created_at)}")
            st.write(turn.answer)
            if turn.citations:
                st.markdown('**Documentation sources**')
            for index, citation in enumerate(turn.citations):
                label = citation.get('heading') or 'Introduction'
                st.link_button(label + ' · ' + citation['file'], f"https://github.com/{ctx.settings.repository}/blob/{citation['approved_commit']}/{citation['file']}", key=f'citation-{turn.id}-{index}')
                with st.expander('Read supporting documentation', key=f'passage-{turn.id}-{index}'):
                    passage = passages.get((turn.knowledge_version_id, citation['section_id']))
                    if passage:
                        st.markdown(passage)
                    else:
                        st.caption('The original indexed passage is unavailable. The citation link retains its approved commit.')
                    st.caption(f"Source commit {short(citation['approved_commit'])} · knowledge {version}")
            if historical:
                st.button('Ask again using current documentation', key='reask-' + turn.id, on_click=reask, args=(turn.question,))
    prompt = st.chat_input('Ask a question about approved documentation', key='question')
    prompt = st.session_state.pop('reask', None) or prompt
    if prompt:
        st.session_state.last_question = prompt
        def answer():
            with st.spinner('Searching approved documentation and preparing your answer…'):
                with ctx.factory() as session:
                    repo = session.get(Repository, ctx.repo_id)
                    answer_question(session, ctx.settings, repo, prompt, embedder(ctx.settings.embedding_model, ctx.settings.embedding_cache))
        action(answer, 'Answer saved with its approved documentation sources.')
    if st.session_state.get('last_question') and not prompt:
        with st.expander('Retry a previous question'):
            st.write(st.session_state.last_question)
            st.button('Ask again', on_click=reask, args=(st.session_state.last_question,))
