from docsync.ui.onboarding import parse_bulk_selection


def test_parse_bulk_selection_accepts_newlines_commas_and_dedupes():
    options = [
        "docs/PRODUCT.md",
        "docs/design/ARCHITECTURE.md",
        "backend/services/order_service.py",
    ]
    matched, unmatched = parse_bulk_selection(
        "docs/PRODUCT.md\nbackend/services/order_service.py, docs/design/ARCHITECTURE.md\n"
        "docs/PRODUCT.md",
        options,
    )

    assert matched == [
        "docs/PRODUCT.md",
        "backend/services/order_service.py",
        "docs/design/ARCHITECTURE.md",
    ]
    assert unmatched == []


def test_parse_bulk_selection_reports_unknown_values_without_dropping_matches():
    options = ["a", "b", "c"]
    matched, unmatched = parse_bulk_selection("a, missing\n b\nunknown", options)

    assert matched == ["a", "b"]
    assert unmatched == ["missing", "unknown"]


def test_parse_bulk_selection_ignores_empty_input_and_whitespace():
    matched, unmatched = parse_bulk_selection("  \n,\n   ", ["a"])

    assert matched == []
    assert unmatched == []
