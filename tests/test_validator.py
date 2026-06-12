"""Unit tests for DocumentValidator."""

from __future__ import annotations

from md2pdf.core.validator import DocumentValidator


def test_validator_supported_types() -> None:
    """Verify that supported types do not generate warnings."""
    validator = DocumentValidator()
    tokens = [{"type": "Heading", "children": []}]
    issues = validator.validate(tokens)
    assert len(issues) == 0


def test_validator_unsupported_type() -> None:
    """Verify warning for unsupported token type."""
    validator = DocumentValidator()
    tokens = [{"type": "SomeUnsupportedType", "_node": None}]
    issues = validator.validate(tokens)
    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert issues[0].code == "UNSUPPORTED_ELEMENT"


def test_validator_empty_table() -> None:
    """Verify error for tables with no rows or headers."""
    validator = DocumentValidator()

    class DummyTableNode:
        header = None
        children = []
        line_number = 10

    tokens = [{"type": "Table", "_node": DummyTableNode()}]
    issues = validator.validate(tokens)
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].code == "EMPTY_TABLE"
    assert issues[0].line == 10


def test_validator_nested_table() -> None:
    """Verify error for tables nested within cell nodes."""
    validator = DocumentValidator()

    class Table:
        line_number = 15

    class CellNode:
        children = [Table()]

    class RowNode:
        children = [CellNode()]

    class TableNode:
        header = RowNode()
        children = []
        line_number = 5

    tokens = [{"type": "Table", "_node": TableNode()}]
    issues = validator.validate(tokens)
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].code == "NESTED_TABLE"
    assert issues[0].line == 15


def test_validator_empty_diagram() -> None:
    """Verify error for Mermaid and Latex blocks with empty/blank contents."""
    validator = DocumentValidator()
    tokens = [{"type": "Mermaid", "raw": "   ", "_node": None}]
    issues = validator.validate(tokens)
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].code == "EMPTY_DIAGRAM"
