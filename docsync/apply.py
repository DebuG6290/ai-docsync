from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from docsync.errors import ConflictError
from docsync.repository.markdown_sections import parse_sections, section_sha256
from docsync.store import Store


def apply_case(store: Store, case_id: str) -> list[dict]:
    case = store.case(case_id)
    if case is None:
        raise ValueError(f"Unknown case {case_id}")
    proposals = store.proposals(case_id)
    if not proposals:
        store.event("apply_blocked", {"reason": "case has no proposals"}, case_id)
        raise ValueError("This case has no documentation proposals to apply")
    if any(p["status"] != "ACCEPTED" or not p["accepted_version_id"] for p in proposals):
        store.event("apply_blocked", {"reason": "not every proposal has an explicit accepted version"}, case_id)
        raise ValueError("Every proposal must be explicitly accepted before apply")

    root = Path(case["repo_root"])
    snapshot = store.case_snapshot(case_id)
    by_path: dict[str, list[tuple[object, str, str]]] = {}
    # Validate every target before writing any file.
    for proposal in proposals:
        section = next(s for s in snapshot["sections"] if s["section_id"] == proposal["section_id"])
        file_path = (root / section["path"]).resolve()
        try:
            file_path.relative_to(root.resolve())
        except ValueError as exc:
            store.event("apply_conflict", {"section_id": section["section_id"], "reason": "mapped path escapes repository"}, case_id)
            raise ConflictError(f"Mapped documentation path escapes the repository: {section['path']}") from exc
        try:
            with file_path.open("r", encoding="utf-8", newline="") as stream:
                current = stream.read()
        except OSError as exc:
            store.event("apply_conflict", {"section_id": section["section_id"], "reason": "target file unreadable", "error": str(exc)}, case_id)
            raise ConflictError(f"Cannot read {section['path']}: {exc}") from exc
        parsed = parse_sections(section["path"], current)
        current_section = next((s for s in parsed if s.section_id == section["section_id"]), None)
        if current_section is None:
            store.event("apply_conflict", {"section_id": section["section_id"], "reason": "section missing"}, case_id)
            raise ConflictError(f"Section {section['section_id']} no longer exists; nothing was applied")
        current_hash = section_sha256(current_section.text)
        if current_hash != section["sha256"]:
            store.event("apply_conflict", {"section_id": section["section_id"], "reason": "section hash changed", "base_sha256": section["sha256"], "current_sha256": current_hash}, case_id)
            raise ConflictError(f"Section {section['section_id']} changed since analysis; nothing was applied")
        version = store.db.execute("SELECT * FROM proposal_versions WHERE id=?", (proposal["accepted_version_id"],)).fetchone()
        if version is None or version["proposal_id"] != proposal["id"]:
            raise ValueError(f"Accepted version for proposal {proposal['id']} is missing or invalid")
        by_path.setdefault(str(file_path), []).append((current_section, version["proposed_text"], proposal["id"]))

    staged: dict[Path, tuple[str, dict[str, tuple[str, str]]]] = {}
    for raw_path, replacements in by_path.items():
        file_path = Path(raw_path)
        with file_path.open("r", encoding="utf-8", newline="") as stream:
            original = stream.read()
        line_list = original.splitlines(keepends=True)
        output: list[str] = []
        cursor = 0
        section_hashes: dict[str, tuple[str, str]] = {}
        for section, replacement, proposal_id in sorted(replacements, key=lambda item: item[0].start_line):
            output.extend(line_list[cursor : section.start_line])
            newline = "\r\n" if "\r\n" in section.text else "\n"
            replacement_text = replacement.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
            if replacement_text and not replacement_text.endswith(("\n", "\r")):
                # Match a section boundary newline if the replaced section had one.
                if section.text.endswith(("\n", "\r")):
                    replacement_text += "\n"
            output.append(replacement_text)
            cursor = section.end_line
            section_hashes[proposal_id] = (section.section_id, section_sha256(replacement_text))
        output.extend(line_list[cursor:])
        staged[file_path] = ("".join(output), section_hashes)

    temps: list[tuple[Path, Path]] = []
    try:
        for target, (content, _hashes) in staged.items():
            fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.docsync-", dir=target.parent)
            temp = Path(temp_name)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
            temps.append((temp, target))
        for temp, target in temps:
            os.replace(temp, target)
    except OSError as exc:
        for temp, _target in temps:
            temp.unlink(missing_ok=True)
        raise ConflictError(f"Could not complete patch application: {exc}") from exc

    results: list[dict] = []
    for target, (content, section_hashes) in staged.items():
        file_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        for proposal in proposals:
            if proposal["id"] not in section_hashes:
                continue
            sid, section_sha = section_hashes[proposal["id"]]
            store.set_proposal_status(proposal["id"], "APPLIED", applied_sha256=section_sha)
            results.append({"section_id": sid, "path": str(target), "section_sha256": section_sha, "file_sha256": file_sha})
    store.db.execute("UPDATE cases SET status='APPLIED' WHERE id=?", (case_id,))
    store.db.commit()
    store.event("patch_applied", {"results": results}, case_id)
    return results

