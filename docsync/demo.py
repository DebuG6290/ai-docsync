"""Isolated, offline product walkthrough using real approval/indexing services.

Suggestions and GitHub merge events are sample fixtures, never live AI results.
No production settings, GitHub client, embeddings download or network calls.
"""
from dataclasses import dataclass
import hashlib

from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from docsync.repository.markdown_sections import parse_sections, section_sha256
from docsync.web.database import initialize_database, session_factory
from docsync.web.indexing import IndexInput, replace_approved_sections, retrieve
from docsync.web.models import (Repository, ChangeCase, SectionAssessment, Proposal, ProposalVersion,
    DocumentationRelease, ReleaseSection, AuditEvent)
from docsync.web.workflow import accept_proposal, modify_proposal, audit
from docsync.security import actor_scope, local_principal

BEFORE = '## Default timeout\nThe client waits up to five seconds before timing out.\n'
AFTER = '## Default timeout\nThe client waits up to eight seconds before timing out.\n'
PATH = 'docs/client.md'
SECTION = parse_sections(PATH, BEFORE)[0]


class SampleEmbedder:
    """One sample section: fixed vector, explicitly not semantic retrieval."""
    def embed(self, _text):
        return [1.] + [0.] * 383


@dataclass
class DemoWorkspace:
    engine: object
    factory: object
    repo_id: str
    proposal_id: str
    case_id: str

    def snapshot(self):
        with self.factory() as session:
            repo = session.get(Repository, self.repo_id)
            proposal = session.get(Proposal, self.proposal_id)
            latest = session.scalar(select(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id)
                .order_by(ProposalVersion.version.desc()).limit(1))
            version, chunks = retrieve(session, repo, SampleEmbedder().embed('timeout'))
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.created_at, AuditEvent.id)).all()
            return {'proposal': proposal, 'latest': latest, 'version': version,
                'approved_text': ''.join(c.content for c in chunks), 'events': events,
                'activated': session.get(ChangeCase, self.case_id).status == 'INDEXED'}

    def save_edit(self, content):
        with actor_scope(local_principal('sample-reviewer')), self.factory() as session:
            modify_proposal(session, self.proposal_id, content)

    def approve(self):
        with actor_scope(local_principal('sample-reviewer')), self.factory() as session:
            proposal = session.get(Proposal, self.proposal_id)
            latest = session.scalar(select(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id)
                .order_by(ProposalVersion.version.desc()).limit(1))
            accept_proposal(session, proposal.id, latest.id)

    def simulate_merge(self):
        with actor_scope(local_principal('sample-reviewer')), self.factory() as session:
            proposal = session.get(Proposal, self.proposal_id)
            if proposal.status != 'ACCEPTED' or not proposal.accepted_version_id:
                raise ValueError('Approve the exact documentation version before simulating a merge')
            if session.scalar(select(DocumentationRelease.id).where(DocumentationRelease.case_id == self.case_id)):
                raise ValueError('This sample update is already activated')
            accepted = session.get(ProposalVersion, proposal.accepted_version_id)
            case = session.get(ChangeCase, self.case_id)
            repo = session.get(Repository, self.repo_id)
            release = DocumentationRelease(case_id=case.id, repo_id=repo.id, branch='sample/approved-docs',
                commit_sha='c' * 40, pr_number=0, pr_url='', status='MERGED', merged_sha='c' * 40)
            session.add(release)
            session.flush()
            session.add(ReleaseSection(release_id=release.id, section_id=SECTION.section_id, path=PATH,
                text=accepted.proposed_text, sha256=hashlib.sha256(accepted.proposed_text.encode()).hexdigest()))
            audit(session, 'sample_merge_simulated', {'repo_id': repo.id, 'simulated': True}, case.id)
            replace_approved_sections(session, repo, 'c' * 40,
                [IndexInput(SECTION.section_id, PATH, SECTION.heading, accepted.proposed_text, 'c' * 40)],
                SampleEmbedder(), case=case, release=release)
            audit(session, 'sample_knowledge_activated', {'repo_id': repo.id, 'simulated': True}, case.id)
            session.commit()


def create_demo():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    initialize_database(engine)
    factory = session_factory(engine)
    with factory() as session:
        repo = Repository(full_name='example/docsync-sample', monitored_branch='main')
        session.add(repo)
        session.flush()
        replace_approved_sections(session, repo, 'a' * 40,
            [IndexInput(SECTION.section_id, PATH, SECTION.heading, BEFORE, 'a' * 40)], SampleEmbedder())
        case = ChangeCase(repo_id=repo.id, before_sha='a' * 40, after_sha='b' * 40,
            status='READY_FOR_REVIEW', decision='UPDATE', summary='Sample: the default timeout changes from 5 to 8 seconds.', case_data={})
        session.add(case)
        session.flush()
        session.add(SectionAssessment(case_id=case.id, section_id=SECTION.section_id, path=PATH,
            heading=SECTION.heading, current_text=BEFORE, base_sha256=section_sha256(BEFORE),
            start_line=SECTION.start_line, end_line=SECTION.end_line, decision='UPDATE',
            rationale='Sample suggestion: align the documented default with the changed constant.',
            evidence_completeness='COMPLETE', proposed_text=AFTER))
        proposal = Proposal(case_id=case.id, section_id=SECTION.section_id, status='PENDING')
        session.add(proposal)
        session.flush()
        session.add(ProposalVersion(proposal_id=proposal.id, version=1, author='sample-fixture',
            human_modified=False, proposed_text=AFTER, reason='Scripted sample suggestion, not a live AI result.'))
        audit(session, 'sample_workspace_created', {'repo_id': repo.id, 'simulated': True})
        session.commit()
        return DemoWorkspace(engine, factory, repo.id, proposal.id, case.id)


def main():
    """Installed command, with a loopback binding by default."""
    import subprocess
    import sys
    from pathlib import Path
    target = Path(__file__).with_name('ui') / 'demo.py'
    raise SystemExit(subprocess.call([sys.executable, '-m', 'streamlit', 'run', str(target),
        '--server.address=127.0.0.1', *sys.argv[1:]]))
