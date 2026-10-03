import hashlib

import pytest

from docsync.apply import apply_case
from docsync.errors import ConflictError
from docsync.repository.markdown_sections import parse_sections, to_doc_section
from docsync.sarvam import ModelClient
from docsync.store import Store


def _case(store: Store, repo, path="guide.md"):
    markdown = "## Timeouts\nThe default is five seconds.\n## Other\nKeep this.\n"
    (repo / path).write_text(markdown, encoding="utf-8")
    section = to_doc_section(parse_sections(path, markdown)[0]).model_dump()
    parsed = parse_sections(path, markdown)[0]
    section.update(start_line=parsed.start_line, end_line=parsed.end_line)
    case_id = store.create_case({
        "repo_root": str(repo), "old_sha": "a" * 40, "new_sha": "b" * 40,
        "changes": [{"code_id": "pkg/core.py::DEFAULT", "name": "DEFAULT", "kind": "assignment", "change_kind": "modified", "diff": "+DEFAULT = 8"}],
        "mappings": [{"code_id": "pkg/core.py::DEFAULT", "section_id": section["section_id"], "reason": "human confirmed"}],
        "sections": [section],
    })
    store.set_case_result(case_id, "UPDATE", "Default changed", "READY")
    pid = store.add_proposal(case_id, section["section_id"], "## Timeouts\nThe default is eight seconds.\n", "The configured default changed.", ["DEFAULT = 8"])
    return case_id, pid, section["section_id"]


def test_apply_requires_explicit_acceptance_and_records_hash(tmp_path):
    store = Store(tmp_path / "audit.sqlite3")
    repo = tmp_path / "repo"
    repo.mkdir()
    case_id, proposal_id, section_id = _case(store, repo)
    with pytest.raises(ValueError, match="explicitly accepted"):
        apply_case(store, case_id)
    version = store.latest_version(proposal_id)
    store.review_event(proposal_id, "ACCEPT", version["id"])
    store.set_proposal_status(proposal_id, "ACCEPTED", accepted_version_id=version["id"])

    result = apply_case(store, case_id)

    assert "eight seconds" in (repo / "guide.md").read_text(encoding="utf-8")
    assert result[0]["section_id"] == section_id
    assert result[0]["section_sha256"] == hashlib.sha256(
        "## Timeouts\nThe default is eight seconds.\n".encode()
    ).hexdigest()
    assert any(row["kind"] == "patch_applied" for row in store.audit(case_id))


def test_apply_stops_on_stale_section_without_overwriting(tmp_path):
    store = Store(tmp_path / "audit.sqlite3")
    repo = tmp_path / "repo"
    repo.mkdir()
    case_id, proposal_id, _section_id = _case(store, repo)
    version = store.latest_version(proposal_id)
    store.set_proposal_status(proposal_id, "ACCEPTED", accepted_version_id=version["id"])
    current = (repo / "guide.md").read_text(encoding="utf-8")
    (repo / "guide.md").write_text(current.replace("five", "six"), encoding="utf-8")

    with pytest.raises(ConflictError, match="changed since analysis"):
        apply_case(store, case_id)
    assert "six seconds" in (repo / "guide.md").read_text(encoding="utf-8")
    assert store.proposal(proposal_id)["status"] == "ACCEPTED"
    assert any(row["kind"] == "apply_conflict" for row in store.audit(case_id))


def test_execution_error_is_not_stored_as_semantic_uncertain(tmp_path):
    store = Store(tmp_path / "audit.sqlite3")
    repo = tmp_path / "repo"
    repo.mkdir()
    case_id, _proposal_id, _section_id = _case(store, repo)

    store.set_case_error(case_id, "Sarvam output was truncated")

    case = store.case(case_id)
    assert case["status"] == "ERROR"
    assert case["decision"] is None
    assert case["summary"] == "Sarvam output was truncated"


def test_one_stale_target_prevents_changes_to_every_target(tmp_path):
    store = Store(tmp_path / "audit.sqlite3")
    repo = tmp_path / "repo"
    repo.mkdir()
    content_a = "## Timeouts\nFive seconds.\n"
    content_b = "## Quickstart\nFive seconds.\n"
    (repo / "a.md").write_text(content_a, encoding="utf-8")
    (repo / "b.md").write_text(content_b, encoding="utf-8")
    sections = []
    mappings = []
    for path, content in [("a.md", content_a), ("b.md", content_b)]:
        parsed = parse_sections(path, content)[0]
        sections.append({**to_doc_section(parsed).model_dump(), "start_line": parsed.start_line, "end_line": parsed.end_line})
        mappings.append({"code_id": "pkg/core.py::DEFAULT", "section_id": parsed.section_id, "reason": "human confirmed"})
    case_id = store.create_case({"repo_root": str(repo), "old_sha": "a"*40, "new_sha": "b"*40, "changes": [], "mappings": mappings, "sections": sections})
    store.set_case_result(case_id, "UPDATE", "Default changed", "READY")
    for section in sections:
        proposal_id = store.add_proposal(case_id, section["section_id"], section["text"].replace("Five", "Eight"), "Default changed", ["DEFAULT = 8"])
        version = store.latest_version(proposal_id)
        store.set_proposal_status(proposal_id, "ACCEPTED", accepted_version_id=version["id"])
    (repo / "b.md").write_text(content_b.replace("Five", "Six"), encoding="utf-8")

    with pytest.raises(ConflictError, match="changed since analysis"):
        apply_case(store, case_id)

    assert (repo / "a.md").read_text(encoding="utf-8") == content_a
    assert "Six seconds" in (repo / "b.md").read_text(encoding="utf-8")


def test_revision_and_review_records_are_append_only(tmp_path):
    store = Store(tmp_path / "audit.sqlite3")
    repo = tmp_path / "repo"
    repo.mkdir()
    case_id, proposal_id, _section_id = _case(store, repo)
    first = store.latest_version(proposal_id)
    store.review_event(proposal_id, "REJECT", first["id"], reason="Preserve network inactivity.")
    second_id = store.add_version(proposal_id, "V2 text", "Revision", ["DEFAULT = 8"], "sarvam")
    store.review_event(proposal_id, "MODIFY", second_id, content="human version")
    store.add_version(proposal_id, "Human final", "Human-authored modification", [], "human")

    versions = store.versions(proposal_id)
    events = store.db.execute("SELECT action, reason FROM review_events WHERE proposal_id=? ORDER BY created_at", (proposal_id,)).fetchall()
    assert [v["version"] for v in versions] == [1, 2, 3]
    assert versions[-1]["author"] == "human"
    assert [e["action"] for e in events] == ["REJECT", "MODIFY"]
    assert store.case(case_id) is not None


def test_review_rejection_revises_only_targeted_proposal(tmp_path, monkeypatch, capsys):
    from docsync import cli
    import json

    store = Store(tmp_path / "audit.sqlite3")
    repo = tmp_path / "repo"
    repo.mkdir()
    markdown = "## Quickstart\nThe default is five seconds.\n## Timeouts\nAlso five seconds.\n"
    (repo / "guide.md").write_text(markdown, encoding="utf-8")
    parsed = parse_sections("guide.md", markdown)
    sections = []
    mappings = []
    for section in parsed:
        sections.append({**to_doc_section(section).model_dump(), "start_line": section.start_line, "end_line": section.end_line})
        mappings.append({"code_id": "pkg/core.py::DEFAULT", "section_id": section.section_id, "reason": "human confirmed"})
    case_id = store.create_case({"repo_root": str(repo), "old_sha": "a"*40, "new_sha": "b"*40, "changes": [{"code_id": "pkg/core.py::DEFAULT", "name": "DEFAULT", "kind": "assignment", "change_kind": "modified", "diff": "+DEFAULT = 8"}], "mappings": mappings, "sections": sections})
    store.set_case_result(case_id, "UPDATE", "Default changed", "READY")
    for section in sections:
        store.add_proposal(case_id, section["section_id"], section["text"], "Initial proposal", ["DEFAULT = 8"])
    ordered = store.proposals(case_id)
    target = ordered[0]
    other = ordered[1]
    other_text = store.latest_version(other["id"])["proposed_text"]

    class RevisionClient(ModelClient):
        def complete(self, system, user, schema_name, schema):
            context = json.loads(user)
            current = context["current_approved_documentation"]["text"]
            return json.dumps({
                "section_id": context["target_section_id"],
                "proposed_text": current + "Revised with network inactivity context.\n",
                "reason": "Addresses the reviewer request.",
                "code_evidence": ["DEFAULT = 8"],
                "evidence_completeness": "COMPLETE",
                "missing_information": [],
                "safe_claims": ["The default is eight seconds of network inactivity."],
                "unsupported_claims": [],
            })

    client = RevisionClient()
    monkeypatch.setattr(cli, "SarvamClient", lambda _model: client)
    input_values = iter(["R", "Preserve network inactivity wording.", "A", "A"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(input_values))

    cli._review(store, case_id, "sarvam-105b")

    target_versions = store.versions(target["id"])
    other_versions = store.versions(other["id"])
    assert len(target_versions) == 2
    assert target_versions[0]["proposed_text"] == sections[next(i for i,s in enumerate(sections) if s["section_id"] == target["section_id"])]["text"]
    assert "Revised with network inactivity context" in target_versions[1]["proposed_text"]
    assert len(other_versions) == 1 and other_versions[0]["proposed_text"] == other_text
    assert store.proposal(target["id"])["status"] == "ACCEPTED"
    assert [row["action"] for row in store.db.execute("SELECT action FROM review_events WHERE proposal_id=? ORDER BY created_at", (target["id"],))] == ["REJECT", "ACCEPT"]
    assert "CODE CHANGE / EVIDENCE" in capsys.readouterr().out


def test_human_modify_is_stored_and_accepted_without_model_call(tmp_path, monkeypatch):
    from docsync import cli

    store = Store(tmp_path / "audit.sqlite3")
    repo = tmp_path / "repo"
    repo.mkdir()
    case_id, proposal_id, _section_id = _case(store, repo)
    human_text = "## Timeouts\nThis is my exact wording.\n"
    input_values = iter(["M", "## Timeouts", "This is my exact wording.", ".", "A"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(input_values))
    monkeypatch.setattr(cli, "SarvamClient", lambda *_args, **_kwargs: pytest.fail("Human edits must not call Sarvam"))

    cli._review(store, case_id, "sarvam-105b")

    versions = store.versions(proposal_id)
    assert len(versions) == 2
    assert versions[1]["author"] == "human" and versions[1]["proposed_text"] == human_text
    proposal = store.proposal(proposal_id)
    assert proposal["status"] == "ACCEPTED" and proposal["accepted_version_id"] == versions[1]["id"]
    events = store.db.execute("SELECT action, content FROM review_events WHERE proposal_id=? ORDER BY created_at", (proposal_id,)).fetchall()
    assert [item["action"] for item in events] == ["MODIFY", "ACCEPT"]
    assert events[0]["content"] == human_text

