from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """SQLite audit store. Proposal revisions and events are insert-only."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS mappings (
              code_id TEXT NOT NULL, section_id TEXT NOT NULL, status TEXT NOT NULL,
              reason TEXT NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY(code_id, section_id)
            );
            CREATE TABLE IF NOT EXISTS mapping_suggestions (
              id TEXT PRIMARY KEY, code_id TEXT NOT NULL, section_id TEXT NOT NULL,
              reason TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cases (
              id TEXT PRIMARY KEY, repo_root TEXT NOT NULL, old_sha TEXT NOT NULL,
              new_sha TEXT NOT NULL, status TEXT NOT NULL, decision TEXT,
              summary TEXT, input_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS case_mappings (
              case_id TEXT NOT NULL REFERENCES cases(id), code_id TEXT NOT NULL,
              section_id TEXT NOT NULL, reason TEXT NOT NULL,
              PRIMARY KEY(case_id, code_id, section_id)
            );
            CREATE TABLE IF NOT EXISTS case_sections (
              case_id TEXT NOT NULL REFERENCES cases(id), section_id TEXT NOT NULL,
              path TEXT NOT NULL, heading TEXT NOT NULL, text TEXT NOT NULL,
              sha256 TEXT NOT NULL, start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
              PRIMARY KEY(case_id, section_id)
            );
            CREATE TABLE IF NOT EXISTS proposals (
              id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
              section_id TEXT NOT NULL, status TEXT NOT NULL,
              accepted_version_id TEXT, applied_sha256 TEXT,
              UNIQUE(case_id, section_id)
            );
            CREATE TABLE IF NOT EXISTS proposal_versions (
              id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id),
              version INTEGER NOT NULL, author TEXT NOT NULL, proposed_text TEXT NOT NULL,
              reason TEXT NOT NULL, code_evidence_json TEXT NOT NULL,
              created_at TEXT NOT NULL, UNIQUE(proposal_id, version)
            );
            CREATE TABLE IF NOT EXISTS review_events (
              id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id),
              action TEXT NOT NULL, version_id TEXT, reason TEXT, content TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
              id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id),
              kind TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """
        )
        self.db.commit()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def event(self, kind: str, payload: dict[str, Any], case_id: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), case_id, kind, self._json(payload), now()),
        )
        self.db.commit()

    def add_mapping_suggestion(self, code_id: str, section_id: str, reason: str) -> str:
        sid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO mapping_suggestions VALUES (?, ?, ?, ?, 'PENDING', ?)",
            (sid, code_id, section_id, reason, now()),
        )
        self.db.commit()
        self.event("mapping_suggested", {"id": sid, "code_id": code_id, "section_id": section_id, "reason": reason})
        return sid

    def suggestions(self) -> list[sqlite3.Row]:
        return list(self.db.execute("SELECT * FROM mapping_suggestions WHERE status='PENDING' ORDER BY created_at"))

    def confirm_suggestion(self, sid: str, approved: bool) -> None:
        row = self.db.execute("SELECT * FROM mapping_suggestions WHERE id=?", (sid,)).fetchone()
        if row is None or row["status"] != "PENDING":
            raise ValueError(f"No pending mapping suggestion {sid}")
        status = "APPROVED" if approved else "REJECTED"
        self.db.execute("UPDATE mapping_suggestions SET status=? WHERE id=?", (status, sid))
        if approved:
            self.db.execute(
                "INSERT OR REPLACE INTO mappings VALUES (?, ?, 'APPROVED', ?, ?)",
                (row["code_id"], row["section_id"], row["reason"], now()),
            )
        self.db.commit()
        self.event("mapping_reviewed", {"id": sid, "status": status, "code_id": row["code_id"], "section_id": row["section_id"]})

    def add_confirmed_mapping(self, code_id: str, section_id: str, reason: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO mappings VALUES (?, ?, 'APPROVED', ?, ?)",
            (code_id, section_id, reason, now()),
        )
        self.db.commit()
        self.event("mapping_imported_as_confirmed", {"code_id": code_id, "section_id": section_id, "reason": reason})

    def mappings_for(self, code_ids: set[str]) -> list[sqlite3.Row]:
        if not code_ids:
            return []
        marks = ",".join("?" for _ in code_ids)
        return list(self.db.execute(
            f"SELECT * FROM mappings WHERE status='APPROVED' AND code_id IN ({marks}) ORDER BY code_id, section_id",
            tuple(sorted(code_ids)),
        ))

    def create_case(self, case: dict[str, Any]) -> str:
        case_id = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO cases VALUES (?, ?, ?, ?, 'ANALYZING', NULL, NULL, ?, ?)",
            (case_id, case["repo_root"], case["old_sha"], case["new_sha"], self._json(case), now()),
        )
        for m in case["mappings"]:
            self.db.execute("INSERT INTO case_mappings VALUES (?, ?, ?, ?)", (case_id, m["code_id"], m["section_id"], m["reason"]))
        for s in case["sections"]:
            self.db.execute(
                "INSERT INTO case_sections VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (case_id, s["section_id"], s["path"], s["heading"], s["text"], s["sha256"], s["start_line"], s["end_line"]),
            )
        self.db.commit()
        self.event("case_created", {"old_sha": case["old_sha"], "new_sha": case["new_sha"]}, case_id)
        return case_id

    def set_case_result(self, case_id: str, decision: str, summary: str, status: str) -> None:
        self.db.execute("UPDATE cases SET decision=?, summary=?, status=? WHERE id=?", (decision, summary, status, case_id))
        self.db.commit()
        self.event("impact_decision", {"decision": decision, "summary": summary}, case_id)

    def set_case_error(self, case_id: str, message: str) -> None:
        """Persist execution failure without mislabeling it as semantic UNCERTAIN."""
        self.db.execute(
            "UPDATE cases SET decision=NULL, summary=?, status='ERROR' WHERE id=?",
            (message, case_id),
        )
        self.db.commit()

    def add_proposal(self, case_id: str, section_id: str, text: str, reason: str, evidence: list[str], author: str = "sarvam") -> str:
        pid = str(uuid.uuid4())
        self.db.execute("INSERT INTO proposals VALUES (?, ?, ?, 'PENDING', NULL, NULL)", (pid, case_id, section_id))
        self.add_version(pid, text, reason, evidence, author)
        self.event("proposal_created", {"proposal_id": pid, "section_id": section_id}, case_id)
        return pid

    def add_version(self, proposal_id: str, text: str, reason: str, evidence: list[str], author: str) -> str:
        version = self.db.execute("SELECT COALESCE(MAX(version), 0)+1 FROM proposal_versions WHERE proposal_id=?", (proposal_id,)).fetchone()[0]
        vid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO proposal_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (vid, proposal_id, version, author, text, reason, self._json(evidence), now()),
        )
        self.db.commit()
        proposal = self.proposal(proposal_id)
        self.event("proposal_version_created", {"proposal_id": proposal_id, "version_id": vid, "version": version, "author": author}, proposal["case_id"] if proposal else None)
        return vid

    def case(self, case_id: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()

    def case_snapshot(self, case_id: str) -> dict[str, Any]:
        row = self.case(case_id)
        if row is None:
            raise ValueError(f"Unknown case {case_id}")
        return json.loads(row["input_json"])

    def proposals(self, case_id: str) -> list[sqlite3.Row]:
        return list(self.db.execute("SELECT * FROM proposals WHERE case_id=? ORDER BY section_id", (case_id,)))

    def proposal(self, proposal_id: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()

    def versions(self, proposal_id: str) -> list[sqlite3.Row]:
        return list(self.db.execute("SELECT * FROM proposal_versions WHERE proposal_id=? ORDER BY version", (proposal_id,)))

    def latest_version(self, proposal_id: str) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM proposal_versions WHERE proposal_id=? ORDER BY version DESC LIMIT 1", (proposal_id,)).fetchone()
        if row is None:
            raise ValueError(f"Proposal {proposal_id} has no versions")
        return row

    def review_event(self, proposal_id: str, action: str, version_id: str | None = None, reason: str | None = None, content: str | None = None) -> None:
        self.db.execute("INSERT INTO review_events VALUES (?, ?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), proposal_id, action, version_id, reason, content, now()))
        self.db.commit()
        proposal = self.proposal(proposal_id)
        self.event("review_" + action.lower(), {"proposal_id": proposal_id, "version_id": version_id, "reason": reason, "content": content}, proposal["case_id"] if proposal else None)

    def set_proposal_status(self, proposal_id: str, status: str, accepted_version_id: str | None = None, applied_sha256: str | None = None) -> None:
        self.db.execute("UPDATE proposals SET status=?, accepted_version_id=COALESCE(?, accepted_version_id), applied_sha256=COALESCE(?, applied_sha256) WHERE id=?", (status, accepted_version_id, applied_sha256, proposal_id))
        self.db.commit()

    def proposal_context(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"Unknown proposal {proposal_id}")
        case = self.case_snapshot(proposal["case_id"])
        section = next(s for s in case["sections"] if s["section_id"] == proposal["section_id"])
        return {"proposal": proposal, "case": case, "section": section, "versions": self.versions(proposal_id)}

    def audit(self, case_id: str) -> list[sqlite3.Row]:
        return list(self.db.execute("SELECT * FROM audit_events WHERE case_id=? ORDER BY created_at, id", (case_id,)))

