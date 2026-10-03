from __future__ import annotations

import difflib
import hmac
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from docsync.web.chat import answer_question, chat_history
from docsync.web.config import Settings, get_settings
from docsync.web.database import initialize_database, make_engine, session_factory
from docsync.web.embeddings import SentenceEmbedder
from docsync.web.github import valid_signature
from docsync.web.models import (
    AuditEvent,
    ChangeCase,
    DocumentationRelease,
    GitHubDelivery,
    Job,
    KnowledgeVersion,
    Proposal,
    ProposalVersion,
    Repository,
    ReviewAction,
    SectionAssessment,
)
from docsync.web.repository import accept_delivery, enqueue, ensure_repository
from docsync.web.workflow import accept_proposal, modify_proposal, reject_proposal, triage_section

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def create_app(settings: Settings | None = None, engine=None) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or make_engine(settings.database_url)
    factory = session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        initialize_database(engine)
        if settings.repository:
            with factory() as session:
                ensure_repository(session, settings, settings.github_installation_id)
                session.commit()
        yield

    app = FastAPI(title="DocSync Review", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(TEMPLATE_DIR.parent / "static")), name="static")
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.embedder = SentenceEmbedder(settings.embedding_model, settings.embedding_cache)
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    security = HTTPBasic(auto_error=False)

    @app.middleware("http")
    async def csrf_cookie(request: Request, call_next):
        token = request.cookies.get("docsync_csrf") or secrets.token_urlsafe(32)
        request.state.docsync_csrf = token
        response = await call_next(request)
        if not request.cookies.get("docsync_csrf"):
            response.set_cookie(
                "docsync_csrf", token, max_age=28800, path="/", secure=request.url.scheme == "https",
                httponly=False, samesite="strict",
            )
        return response

    def require_user(credentials: HTTPBasicCredentials | None = Depends(security)) -> str:
        if not settings.review_password:
            raise HTTPException(status_code=503, detail="DOCSYNC_REVIEW_PASSWORD is not configured")
        if credentials is None:
            raise HTTPException(status_code=401, detail="Sign in to DocSync", headers={"WWW-Authenticate": "Basic"})
        valid_name = hmac.compare_digest(credentials.username.encode(), settings.review_username.encode())
        valid_password = hmac.compare_digest(credentials.password.encode(), settings.review_password.encode())
        if not (valid_name and valid_password):
            raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Basic"})
        return credentials.username

    def require_csrf(request: Request, csrf_token: str = Form(...)) -> None:
        cookie = request.cookies.get("docsync_csrf", "")
        if not cookie or not hmac.compare_digest(cookie, csrf_token):
            raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")

    def current_repository(session: Session) -> Repository:
        if not settings.repository:
            raise HTTPException(status_code=503, detail="DOCSYNC_REPOSITORY is not configured")
        repository = session.scalar(select(Repository).where(Repository.full_name == settings.repository))
        if repository is None:
            repository = ensure_repository(session, settings, settings.github_installation_id)
            session.commit()
        return repository

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/webhooks/github")
    async def github_webhook(request: Request):
        raw_body = await request.body()
        headers = request.headers
        if not valid_signature(settings.github_webhook_secret, raw_body, headers.get("x-hub-signature-256")):
            raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")
        delivery_id = headers.get("x-github-delivery")
        event_name = headers.get("x-github-event")
        if not delivery_id or not event_name:
            raise HTTPException(status_code=400, detail="GitHub delivery headers are required")
        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Webhook body is not valid JSON") from exc
        with factory() as session:
            try:
                status, duplicate = accept_delivery(session, settings, delivery_id, event_name, payload)
            except PermissionError:
                session.rollback()
                raise HTTPException(status_code=404, detail="Repository is not configured")
        return JSONResponse({"received": True, "duplicate": duplicate, "status": status}, status_code=200 if duplicate else 202)

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, _user: str = Depends(require_user)):
        with factory() as session:
            repo = session.scalar(select(Repository).where(Repository.full_name == settings.repository)) if settings.repository else None
            cases = session.scalars(select(ChangeCase).order_by(ChangeCase.created_at.desc()).limit(50)).all()
            active = session.get(KnowledgeVersion, repo.active_index_version_id) if repo and repo.active_index_version_id else None
            deliveries = session.scalars(select(GitHubDelivery).order_by(GitHubDelivery.received_at.desc()).limit(12)).all()
            jobs = session.scalars(select(Job).order_by(Job.created_at.desc()).limit(20)).all()
            return templates.TemplateResponse(
                request=request,
                name="dashboard.html",
                context={"repo": repo, "cases": cases, "active_index": active, "deliveries": deliveries, "jobs": jobs, "csrf_token": request.state.docsync_csrf},
            )

    @app.post("/admin/index-baseline")
    def index_baseline(_csrf: None = Depends(require_csrf), _user: str = Depends(require_user)):
        with factory() as session:
            repo = current_repository(session)
            if repo.active_index_version_id:
                raise HTTPException(status_code=409, detail="An active approved index already exists")
            if repo.installation_id is None:
                raise HTTPException(status_code=409, detail="Set GITHUB_INSTALLATION_ID before indexing the baseline")
            pending = session.scalar(
                select(Job.id).where(
                    Job.repo_id == repo.id,
                    Job.kind == "index_baseline",
                    Job.status.in_(["PENDING", "PROCESSING"]),
                ).limit(1)
            )
            if pending is None:
                enqueue(session, repo.id, "index_baseline", {})
            session.commit()
        return RedirectResponse("/", status_code=303)

    @app.get("/cases/{case_id}", response_class=HTMLResponse)
    def case_detail(request: Request, case_id: str, _user: str = Depends(require_user)):
        with factory() as session:
            case = session.get(ChangeCase, case_id)
            if case is None:
                raise HTTPException(status_code=404, detail="Case not found")
            repo = session.get(Repository, case.repo_id)
            assessments = session.scalars(
                select(SectionAssessment).where(SectionAssessment.case_id == case.id).order_by(SectionAssessment.path, SectionAssessment.start_line)
            ).all()
            proposals = session.scalars(select(Proposal).where(Proposal.case_id == case.id).order_by(Proposal.section_id)).all()
            proposal_cards = []
            for proposal in proposals:
                versions = session.scalars(
                    select(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id).order_by(ProposalVersion.version)
                ).all()
                section = next((item for item in assessments if item.section_id == proposal.section_id), None)
                proposal_cards.append({"proposal": proposal, "versions": versions, "latest": versions[-1] if versions else None, "section": section})
            diffs = {}
            for item in assessments:
                proposal = next((p for p in proposal_cards if p["proposal"].section_id == item.section_id), None)
                if proposal and proposal["latest"]:
                    before = item.current_text.splitlines()
                    after = proposal["latest"].proposed_text.splitlines()
                    diffs[item.section_id] = [
                        {"kind": "add" if line.startswith("+ ") else "remove" if line.startswith("- ") else "same", "text": line[2:]}
                        for line in difflib.ndiff(before, after)
                    ]
            changes = case.case_data.get("changes", [])
            return templates.TemplateResponse(
                request=request,
                name="case.html",
                context={"case": case, "repo": repo, "assessments": assessments, "proposals": proposal_cards, "changes": changes, "diffs": diffs, "csrf_token": request.state.docsync_csrf},
            )

    @app.get("/cases/{case_id}/audit", response_class=HTMLResponse)
    def case_audit(request: Request, case_id: str, _user: str = Depends(require_user)):
        with factory() as session:
            case = session.get(ChangeCase, case_id)
            if case is None:
                raise HTTPException(status_code=404, detail="Case not found")
            events = session.scalars(select(AuditEvent).where(AuditEvent.case_id == case.id).order_by(AuditEvent.created_at, AuditEvent.id)).all()
            return templates.TemplateResponse(request=request, name="audit.html", context={"case": case, "events": events})

    @app.post("/proposals/{proposal_id}/accept")
    def accept(proposal_id: str, _csrf: None = Depends(require_csrf), _user: str = Depends(require_user)):
        with factory() as session:
            try:
                proposal = session.get(Proposal, proposal_id)
                if proposal is None:
                    raise ValueError("Unknown proposal")
                case_id = proposal.case_id
                accept_proposal(session, proposal_id)
            except ValueError as exc:
                session.rollback()
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse(f"/cases/{case_id}", status_code=303)

    @app.post("/proposals/{proposal_id}/modify")
    def modify(proposal_id: str, content: str = Form(...), _csrf: None = Depends(require_csrf), _user: str = Depends(require_user)):
        with factory() as session:
            try:
                proposal = session.get(Proposal, proposal_id)
                if proposal is None:
                    raise ValueError("Unknown proposal")
                case_id = proposal.case_id
                modify_proposal(session, proposal_id, content)
            except ValueError as exc:
                session.rollback()
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse(f"/cases/{case_id}", status_code=303)

    @app.post("/proposals/{proposal_id}/reject")
    def reject(proposal_id: str, reason: str = Form(...), _csrf: None = Depends(require_csrf), _user: str = Depends(require_user)):
        with factory() as session:
            try:
                proposal = session.get(Proposal, proposal_id)
                if proposal is None:
                    raise ValueError("Unknown proposal")
                case_id = proposal.case_id
                reject_proposal(session, proposal_id, reason)
            except ValueError as exc:
                session.rollback()
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse(f"/cases/{case_id}", status_code=303)

    @app.post("/sections/{assessment_id}/triage")
    def triage(
        assessment_id: str,
        resolution: str = Form(...),
        reason: str = Form(...),
        content: str = Form(""),
        _csrf: None = Depends(require_csrf),
        _user: str = Depends(require_user),
    ):
        with factory() as session:
            assessment = session.get(SectionAssessment, assessment_id)
            if assessment is None:
                raise HTTPException(status_code=404, detail="Section not found")
            case_id = assessment.case_id
            try:
                triage_section(session, assessment_id, resolution, reason, content)
            except ValueError as exc:
                session.rollback()
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse(f"/cases/{case_id}", status_code=303)

    @app.get("/chat", response_class=HTMLResponse)
    def chat_page(request: Request, _user: str = Depends(require_user)):
        with factory() as session:
            repo = current_repository(session)
            turns = chat_history(session, repo.id)
            active = session.get(KnowledgeVersion, repo.active_index_version_id) if repo.active_index_version_id else None
            return templates.TemplateResponse(request=request, name="chat.html", context={"repo": repo, "turns": turns, "active_index": active, "error": None, "csrf_token": request.state.docsync_csrf})

    @app.post("/chat", response_class=HTMLResponse)
    def chat_post(request: Request, question: str = Form(...), _csrf: None = Depends(require_csrf), _user: str = Depends(require_user)):
        with factory() as session:
            repo = current_repository(session)
            try:
                answer_question(session, settings, repo, question, app.state.embedder)
            except Exception as exc:
                session.rollback()
                turns = chat_history(session, repo.id)
                active = session.get(KnowledgeVersion, repo.active_index_version_id) if repo.active_index_version_id else None
                return templates.TemplateResponse(
                    request=request,
                    name="chat.html",
                    context={"repo": repo, "turns": turns, "active_index": active, "error": f"{type(exc).__name__}: {exc}", "csrf_token": request.state.docsync_csrf},
                    status_code=502,
                )
        return RedirectResponse("/chat", status_code=303)

    @app.get("/mappings", response_class=HTMLResponse)
    def mappings_page(request: Request, _user: str = Depends(require_user)):
        from docsync.web.models import CodeDocMapping

        with factory() as session:
            repo = current_repository(session)
            mappings = session.scalars(
                select(CodeDocMapping).where(CodeDocMapping.repo_id == repo.id).order_by(CodeDocMapping.code_id, CodeDocMapping.section_id)
            ).all()
            return templates.TemplateResponse(request=request, name="mappings.html", context={"repo": repo, "mappings": mappings})

    return app


app = create_app()
