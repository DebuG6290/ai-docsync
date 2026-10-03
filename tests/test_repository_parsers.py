from docsync.repository.markdown_sections import parse_sections
from docsync.repository.python_symbols import extract_symbols


def test_markdown_preserves_exact_sections_and_ignores_fenced_headings():
    source = "Intro\n\n## Timeouts\nText\n```python\n## not a heading\n```\n## Other\nEnd\n"
    sections = parse_sections("guide.md", source)
    assert [item.section_id for item in sections] == [
        "guide.md::__intro__",
        "guide.md::timeouts",
        "guide.md::other",
    ]
    assert sections[1].text == "## Timeouts\nText\n```python\n## not a heading\n```\n"


def test_python_symbols_have_qualified_stable_ids():
    source = "class Timeout:\n    def as_dict(self):\n        return {'read': 5}\nDEFAULT = 5\n"
    symbols = extract_symbols("pkg/config.py", source)
    assert "pkg/config.py::Timeout" in symbols
    assert "pkg/config.py::Timeout.as_dict" in symbols
    assert "pkg/config.py::DEFAULT" in symbols

