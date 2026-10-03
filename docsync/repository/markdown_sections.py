from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from docsync.models import DocSection

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def slugify(value: str) -> str:
    value = re.sub(r"[`*_~]", "", value).lower()
    value = re.sub(r"[^\w -]", "", value, flags=re.UNICODE)
    return re.sub(r"[\s-]+", "-", value).strip("-") or "section"


def section_sha256(text: str) -> str:
    """Hash canonical LF text so a Git checkout's CRLF policy is not a false conflict."""
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ParsedSection:
    section_id: str
    path: str
    heading: str
    text: str
    start_line: int
    end_line: int


def parse_sections(path: str, text: str) -> list[ParsedSection]:
    """Split on ATX headings while retaining original bytes-as-text for safe patches."""
    lines = text.splitlines(keepends=True)
    headings: list[tuple[int, int, str]] = []
    fence_char: str | None = None
    fence_size = 0
    in_html_comment = False
    for index, line in enumerate(lines):
        clean = line.rstrip("\r\n")
        if in_html_comment:
            if "-->" in clean:
                in_html_comment = False
            continue
        if "<!--" in clean:
            before, _marker, after = clean.partition("<!--")
            if "-->" not in after:
                in_html_comment = True
            clean = before
        fence = _FENCE.match(clean)
        if fence:
            marker = fence.group(1)
            if fence_char is None:
                fence_char, fence_size = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_size:
                fence_char, fence_size = None, 0
            continue
        if fence_char is not None:
            continue
        match = _HEADING.match(clean)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))
    chunks: list[ParsedSection] = []
    boundaries = [0, *(item[0] for item in headings), len(lines)]
    boundaries = sorted(set(boundaries))
    for i, start in enumerate(boundaries[:-1]):
        end = boundaries[i + 1]
        if start == end:
            continue
        heading_tuple = next((h for h in headings if h[0] == start), None)
        heading = heading_tuple[2] if heading_tuple else "(preamble)"
        if heading_tuple:
            depth = heading_tuple[1]
            parent = next(
                (h[2] for h in reversed(headings) if h[0] < start and h[1] < depth),
                None,
            )
            slug = slugify(heading)
            if parent and sum(1 for h in headings if h[2] == heading) > 1:
                slug = f"{slug}--{slugify(parent)}"
            sid = f"{path}::{slug}"
        else:
            sid = f"{path}::__intro__"
        body = "".join(lines[start:end])
        chunks.append(ParsedSection(sid, path, heading, body, start, end))
    return chunks


def to_doc_section(section: ParsedSection) -> DocSection:
    return DocSection(
        section_id=section.section_id,
        path=section.path,
        heading=section.heading,
        text=section.text,
        sha256=section_sha256(section.text),
    )

