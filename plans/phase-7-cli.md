# Phase 7: CLI, Error Reporting & Validation

**Goal:** Harden the CLI, add a structured pre-render validation pass that reports problems with line numbers, improve logging, and make the tool behave well as a scriptable command-line utility.

**Depends on:** All previous phases

---

## Deliverables

- `md2pdf/cli.py` — full CLI with all flags wired to real Pipeline
- `md2pdf/core/validator.py` — `DocumentValidator` (pre-render checks)
- `md2pdf/core/errors.py` — structured error/warning types
- Updated `Pipeline.run()` — validation gate before render
- `tests/test_cli.py` — CLI integration tests via `typer.testing.CliRunner`
- `tests/test_validator.py`

---

## Full CLI (`cli.py`)

```python
import typer
import logging
import sys
from pathlib import Path
from md2pdf.core.config import Config
from md2pdf.core.pipeline import Pipeline
from md2pdf.core.registry import HandlerRegistry
from md2pdf.core.plugin_loader import PluginLoader

app = typer.Typer(
    name="md2pdf",
    help="Convert structured Markdown files to print-ready PDFs.",
    add_completion=False,
)

@app.command()
def convert(
    input: Path = typer.Argument(..., exists=True, help="Input .md file"),
    output: Path = typer.Option(Path("output.pdf"), "-o", "--output",
                                help="Output PDF path"),
    config_file: Path = typer.Option(None, "-c", "--config",
                                     help="Path to md2pdf.toml"),
    theme: str = typer.Option("default", "-t", "--theme", help="Theme name"),
    offline: bool = typer.Option(False, "--offline",
                                  help="Skip external API calls; use placeholders"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Enable debug logging"),
    validate_only: bool = typer.Option(False, "--validate-only",
                                        help="Run validation but do not render"),
) -> None:
    _setup_logging(verbose)

    cfg = Config(
        input_file=str(input),
        output_file=str(output),
        theme=theme,
        offline=offline,
    )
    if config_file:
        cfg = Config.from_toml(str(config_file))
        cfg.input_file = str(input)  # CLI arg takes precedence

    registry = HandlerRegistry()
    loader = PluginLoader(registry, ...)
    loader.load_entry_points()
    loader.load_from_config(cfg.plugins_dict)

    pipeline = Pipeline(cfg, registry)

    raw_md = Path(input).read_text(encoding="utf-8")

    if validate_only:
        issues = pipeline.validate(raw_md)
        _report_issues(issues)
        raise typer.Exit(code=1 if any(i.severity == "error" for i in issues) else 0)

    try:
        pipeline.run(raw_md)
        typer.echo(f"✓ PDF written to: {output}")
    except Exception as exc:
        typer.echo(f"✗ Conversion failed: {exc}", err=True)
        raise typer.Exit(code=1)

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s  %(name)s: %(message)s",
        stream=sys.stderr,
    )

def _report_issues(issues: list) -> None:
    for issue in issues:
        icon = "✗" if issue.severity == "error" else "⚠"
        typer.echo(f"{icon} Line {issue.line}: [{issue.code}] {issue.message}")
```

---

## Structured Error Types (`errors.py`)

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class ValidationIssue:
    severity: Literal["error", "warning"]
    code: str        # e.g. "UNSUPPORTED_ELEMENT", "EMPTY_TABLE", "NESTED_TABLE"
    message: str
    line: int | None = None
    element_type: str | None = None

class Md2PdfError(Exception):
    """Base exception for all md2pdf errors."""

class ParseError(Md2PdfError):
    """Raised when the markdown cannot be parsed."""

class RenderError(Md2PdfError):
    """Raised when PDF generation fails."""

class ConfigError(Md2PdfError):
    """Raised for invalid configuration."""
```

---

## Document Validator (`validator.py`)

The validator walks the token list **before** any rendering and emits `ValidationIssue` objects. It does NOT crash — it accumulates and reports.

```python
from md2pdf.core.errors import ValidationIssue

class DocumentValidator:
    SUPPORTED_TYPES = {
        "Heading", "Paragraph", "List", "ListItem",
        "Table", "BlockQuote", "CodeFence",
        "Mermaid", "LatexBlock", "ThematicBreak",
    }

    def validate(self, tokens: list[dict]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for token in tokens:
            issues.extend(self._check_token(token))
        return issues

    def _check_token(self, token: dict) -> list[ValidationIssue]:
        issues = []
        t = token["type"]

        if t not in self.SUPPORTED_TYPES:
            issues.append(ValidationIssue(
                severity="warning",
                code="UNSUPPORTED_ELEMENT",
                message=f"Token type '{t}' has no registered handler and will be skipped.",
                element_type=t,
                line=self._guess_line(token),
            ))

        if t == "Table":
            issues.extend(self._check_table(token))

        if t in ("Mermaid", "LatexBlock"):
            raw = token.get("raw", "").strip()
            if not raw:
                issues.append(ValidationIssue(
                    severity="error",
                    code="EMPTY_DIAGRAM",
                    message=f"Empty {t} block found — will render as placeholder.",
                    element_type=t,
                ))

        return issues

    def _check_table(self, token: dict) -> list[ValidationIssue]:
        issues = []
        node = token.get("_node")
        if node is None:
            return issues
        rows = getattr(node, "children", [])
        if len(rows) == 0:
            issues.append(ValidationIssue(
                severity="error", code="EMPTY_TABLE",
                message="Table has no rows.", element_type="Table",
            ))
        # Check for nested tables (not supported)
        for row in rows:
            for cell in getattr(row, "children", []):
                cell_content = getattr(cell, "children", [])
                for child in cell_content:
                    if type(child).__name__ == "Table":
                        issues.append(ValidationIssue(
                            severity="error", code="NESTED_TABLE",
                            message="Nested tables are not supported and will be skipped.",
                            element_type="Table",
                        ))
        return issues

    def _guess_line(self, token: dict) -> int | None:
        node = token.get("_node")
        return getattr(node, "line_number", None)
```

---

## Updated `Pipeline.run()` and `Pipeline.validate()`

```python
def validate(self, raw_md: str) -> list[ValidationIssue]:
    md = self._pre_process(raw_md)
    tokens = self._parse(md)
    validator = DocumentValidator()
    return validator.validate(tokens)

def run(self, raw_md: str) -> None:
    issues = self.validate(raw_md)
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    for w in warnings:
        logging.warning("[%s] Line %s: %s", w.code, w.line, w.message)
    if errors:
        for e in errors:
            logging.error("[%s] Line %s: %s", e.code, e.line, e.message)
        # Errors are non-fatal by default (best-effort render); log and continue
        # To make errors fatal, raise RenderError here based on config flag

    md = self._pre_process(raw_md)
    tokens = self._parse(md)
    flowables = self._map(tokens)
    self._render(flowables)
```

---

## CLI Usage Examples

```bash
# Basic conversion
md2pdf report.md -o report.pdf

# With custom config and theme
md2pdf report.md -o report.pdf -c md2pdf.toml -t legal

# Offline mode (no Kroki API calls)
md2pdf report.md -o report.pdf --offline

# Validate only, no PDF output
md2pdf report.md --validate-only

# Verbose debug output
md2pdf report.md -v
```

Expected exit codes:
- `0` — success
- `1` — error (conversion failed or `--validate-only` found errors)

---

## Acceptance Criteria

- [ ] `md2pdf --help` shows all flags with descriptions
- [ ] `md2pdf nonexistent.md` exits with code 1 and a clear error message (file not found)
- [ ] `md2pdf sample.md --validate-only` prints warnings/errors with line numbers and exits 0/1 correctly
- [ ] `md2pdf sample.md -v` outputs DEBUG-level logs to stderr, not stdout
- [ ] `DocumentValidator` flags an unsupported token type as a warning (not an error)
- [ ] `DocumentValidator` flags an empty `Mermaid` block as an error
- [ ] CLI tests via `CliRunner` cover: happy path, missing file, validate-only, offline flag
