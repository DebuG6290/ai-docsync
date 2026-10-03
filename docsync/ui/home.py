import streamlit as st
from docsync.ui.components import heading, empty, case_card, navigate


def render(ctx, view):
    heading('Your documentation, in sync.', 'Review what changed. Approve what matters. Know what Chat is using.', 'WORKSPACE OVERVIEW')
    if not view['active']:
        st.info('This repository needs setup. Confirm code-to-documentation mappings in Settings, then explicitly initialize its approved baseline. Chat and analysis require approved knowledge.')
        st.button('Continue repository setup', on_click=navigate, args=('Settings',), type='primary')
    actionable = [i for i in view['cases'] if i['status'].label in {'Needs attention', 'Human decision needed', 'Ready for review', 'Ready to publish', 'Publication prepared', 'Refresh needs attention', 'Refresh interrupted'}]
    order = {'Needs attention': 0, 'Refresh needs attention': 0, 'Refresh interrupted': 0, 'Human decision needed': 1,
        'Ready for review': 2, 'Ready to publish': 3, 'Publication prepared': 3}
    actionable.sort(key=lambda i: order.get(i['status'].label, 9))
    a, b, c = st.columns(3)
    a.metric('Reviews needing attention', len(actionable))
    b.metric('Documentation updates in progress', len(view['pending']))
    c.metric('Active knowledge', view['version_names'].get(view['active'].id, 'Not initialized') if view['active'] else 'Not initialized')
    st.subheader('Next up')
    if not actionable:
        empty('Nothing needs your review right now', 'New code changes will appear here automatically. You can check approved knowledge or ask Chat a question.')
        st.button('Ask about your documentation', on_click=navigate, args=('Chat',), type='primary')
    for item in actionable[:8]:
        case_card(ctx, item, 'home')
    waiting = [i for i in view['cases'] if i not in actionable][:4]
    if waiting:
        st.subheader('In progress & recently completed')
        for item in waiting:
            case_card(ctx, item, 'activity')
