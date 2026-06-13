"""DocumentValidator — pre-render validation checks on token streams."""

from __future__ import annotations

from md2pdf.core.errors import ValidationIssue


class DocumentValidator:
    """Validator that scans a token list before rendering to check for issues."""

    SUPPORTED_TYPES = {
        "Heading",
        "Paragraph",
        "List",
        "ListItem",
        "Table",
        "BlockQuote",
        "CodeFence",
        "Mermaid",
        "LatexBlock",
        "ThematicBreak",
        "FootnoteDefinition",
        "Admonition",
    }

    def validate(self, tokens: list[dict]) -> list[ValidationIssue]:
        """Validate a list of normalised tokens.

        Args:
            tokens: Normalized token dicts from the parser.

        Returns:
            A list of ValidationIssue objects found in the document.
        """
        issues: list[ValidationIssue] = []
        for token in tokens:
            issues.extend(self._check_token(token))
        return issues

    def _check_token(self, token: dict) -> list[ValidationIssue]:
        issues = []
        t = token.get("type", "")

        if t not in self.SUPPORTED_TYPES:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="UNSUPPORTED_ELEMENT",
                    message=f"Token type '{t}' has no registered handler and will be skipped.",
                    element_type=t,
                    line=self._guess_line(token),
                )
            )

        if t == "Table":
            issues.extend(self._check_table(token))

        if t in ("Mermaid", "LatexBlock"):
            raw = token.get("raw", "").strip()
            if not raw:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="EMPTY_DIAGRAM",
                        message=f"Empty {t} block found — will render as placeholder.",
                        element_type=t,
                        line=self._guess_line(token),
                    )
                )

        # Recursively check children of block containers
        if t in ("List", "ListItem", "BlockQuote", "Admonition"):
            for child in token.get("children", []):
                issues.extend(self._check_token(child))

        return issues

    def _check_table(self, token: dict) -> list[ValidationIssue]:
        issues = []
        node = token.get("_node")
        if node is None:
            return issues

        header = getattr(node, "header", None)
        rows = getattr(node, "children", [])

        if header is None and not rows:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="EMPTY_TABLE",
                    message="Table has no rows.",
                    element_type="Table",
                    line=self._guess_line(token),
                )
            )

        # Check for nested tables (not supported)
        all_rows = ([header] if header else []) + list(rows)
        for row in all_rows:
            for cell in getattr(row, "children", []):
                cell_content = getattr(cell, "children", [])
                for child in cell_content:
                    # mistletoe Node types are objects
                    child_type = type(child).__name__
                    if child_type == "Table":
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                code="NESTED_TABLE",
                                message="Nested tables are not supported and will be skipped.",
                                element_type="Table",
                                line=getattr(child, "line_number", None),
                            )
                        )
        return issues

    def _guess_line(self, token: dict) -> int | None:
        node = token.get("_node")
        return getattr(node, "line_number", None)
