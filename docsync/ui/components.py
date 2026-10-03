import html
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
import streamlit as st

from docsync.online.operations import execute


@dataclass
class Context:
    settings: object
    engine: object
    factory: object
    repo_id: str


def styles():
    st.markdown('<style>' + Path(__file__).with_name('style.css').read_text() + '</style>', unsafe_allow_html=True)


def short(value):
    return value[:7] if value else '—'


def date(value):
    return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).strftime('%d %b %Y · %H:%M UTC') if value else 'Not yet recorded'


def badge(label, tone='neutral'):
    if tone not in {'neutral', 'success', 'warning', 'error', 'progress'}:
        tone = 'neutral'
    st.markdown(f'<span class="ds-badge ds-{tone}">{html.escape(label)}</span>', unsafe_allow_html=True)


def heading(title, subtitle, eyebrow='DOCSYNC'):
    st.markdown(f'<div class="ds-heading"><div class="ds-eyebrow">{html.escape(eyebrow)}</div>'
        f'<h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>', unsafe_allow_html=True)


def case_title(case, section_count=0):
    # Stored identifiers/commit metadata determine the title; model prose never does.
    if section_count:
        return f'{section_count} documentation section' + ('s' if section_count != 1 else '') + ' to review'
    return f'Review code change {short(case.after_sha)}' if case.after_sha else 'Review documentation update'


def summary_preview(text, limit=180):
    value = ' '.join((text or '').split())
    return value if len(value) <= limit else value[:limit - 1].rstrip() + '…'


def prose(text, *, preview=False, clamp=False):
    value = '\n'.join(line for line in (text or '').splitlines() if line.strip() not in {'UPDATE', 'NO_CHANGE', 'UNCERTAIN'})
    value = summary_preview(value) if preview else value
    paragraphs = ''.join('<p>' + html.escape(p) + '</p>' for p in value.split('\n\n') if p.strip())
    st.markdown('<div class="ds-prose' + (' ds-preview' if clamp else '') + '">' + paragraphs + '</div>', unsafe_allow_html=True)


def empty(title, text):
    st.markdown(f'<div class="ds-empty"><div class="ds-empty-mark">✓</div><h3>{html.escape(title)}</h3>'
        f'<p>{html.escape(text)}</p></div>', unsafe_allow_html=True)


def navigate(page, case_id=None):
    st.session_state.page = page
    if case_id:
        st.session_state.case_id = case_id
        st.session_state.pop('section_selector', None)


def notify(text):
    st.session_state.notice = text


def action(call, success):
    from docsync.errors import ConflictError
    try:
        call()
    except (ValueError, ConflictError) as exc:
        st.error(str(exc))
        return False
    except Exception:
        st.error('This action could not finish. Your saved review history is preserved. Check the operation details before retrying.')
        return False
    notify(success)
    st.rerun()


def operation(ctx, job_id, retry=False):
    def run():
        with st.spinner('Saving the result. Keep this page open…'):
            execute(ctx.engine, ctx.settings, job_id, retry=retry, repo_id=ctx.repo_id)
    action(run, 'Operation completed. The saved result is ready to review.')


def knowledge_summary(view):
    active = view['active']
    if not active:
        st.info('Approved knowledge is not initialized. Open Knowledge for the baseline setup instructions.')
        return
    name = view['version_names'].get(active.id, 'Approved version')
    pending = view['pending']
    from docsync.ui.state import release_status
    problems = [release_status(r, view['jobs']) for r in pending]
    message = f'Chat uses {name} · approved snapshot {short(active.source_commit)}'
    if problems:
        status = next((s for s in problems if s.tone == 'error'), problems[0])
        if status.tone in {'error', 'warning', 'progress'} or any(r.merged_sha for r in pending):
            st.warning(message + ' — ' + status.label + '. ' + status.message)
        else:
            st.info(message + ' — A documentation PR is waiting for merge.')
    else:
        st.markdown(f'<div class="ds-knowledge"><span class="ds-dot"></span>'
            f'<strong>{html.escape(name)} · Approved knowledge active</strong>'
            f'<span>Snapshot {html.escape(short(active.source_commit))} · {html.escape(date(active.created_at))}</span></div>', unsafe_allow_html=True)


def case_card(ctx, item, key_prefix='case'):
    case, status = item['case'], item['status']
    with st.container(border=True, key=f'{key_prefix}-{case.id}'):
        left, right = st.columns([4, 1])
        with left:
            badge(status.label, status.tone)
            st.markdown('### ' + case_title(case, len(item['sections'])))
            if case.summary:
                prose(case.summary, preview=True, clamp=True)
            st.caption(f'{ctx.settings.repository} · {short(case.after_sha)} · {date(case.created_at)}')
            st.write(status.message)
            counts = {d: sum(s.decision == d for s in item['sections']) for d in ['UPDATE', 'NO_CHANGE', 'UNCERTAIN']}
            st.caption(f"{counts['UPDATE']} updates suggested · {counts['NO_CHANGE']} no update recommended · {counts['UNCERTAIN']} need human judgment")
        with right:
            if item['required']:
                st.caption(f"{item['approved']} / {item['required']} decisions complete")
            st.button('Open review', key=f'open-{key_prefix}-{case.id}', on_click=navigate, args=('Reviews', case.id), use_container_width=True)
