# Phase 8: Testing, Packaging & Documentation

**Goal:** Establish a complete test suite, package the project for distribution, and write user-facing documentation including the plugin authoring guide.

**Depends on:** All previous phases

---

## Deliverables

- Complete `tests/` suite (unit + integration)
- `tests/fixtures/` — sample markdown files for integration tests
- `pytest.ini` / `[tool.pytest]` config
- `.gitignore` with cache and build artifacts
- `README.md` — user-facing project documentation
- `docs/plugin-authoring.md` — third-party plugin development guide
- `docs/themes.md` — stylesheet/theme system documentation
- `CHANGELOG.md`
- CI-ready test commands (no CI config file required unless user requests)

---

## Test Suite Structure

```
tests/
├── conftest.py                  # shared fixtures (sample docs, tmp paths)
├── fixtures/
│   ├── simple.md               # headings + paragraphs + lists
│   ├── tables.md               # large multi-page table
│   ├── diagrams.md             # mermaid + latex blocks
│   ├── mixed.md                # all element types combined
│   └── front_matter.md        # YAML front matter + content
├── unit/
│   ├── test_registry.py        # HandlerRegistry: register, get, override, entry points
│   ├── test_parser.py          # MarkdownParser: token types, mermaid/latex detection
│   ├── test_handlers.py        # Each handler: correct Flowable types returned
│   ├── test_preprocessors.py   # FrontMatterStripper, IncludeResolver
│   ├── test_validator.py       # DocumentValidator: all issue codes
│   ├── test_cache.py           # AssetCache: hit/miss, hash correctness
│   ├── test_layout.py          # LayoutComposer: bonding logic
│   └── test_style_registry.py  # StyleRegistry merge order
├── integration/
│   ├── test_pipeline.py        # Full pipeline run on fixture files → valid PDF
│   └── test_cli.py             # CLI via CliRunner
└── network/                    # Skipped by default; run with pytest -m network
    └── test_kroki.py           # Real HTTP call to Kroki.io
```

---

## `conftest.py`

```python
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def simple_md() -> str:
    return (FIXTURES / "simple.md").read_text()

@pytest.fixture
def tmp_pdf(tmp_path) -> Path:
    return tmp_path / "output.pdf"

@pytest.fixture
def default_registry():
    from md2pdf.core.registry import HandlerRegistry
    from md2pdf.core.plugin_loader import PluginLoader
    registry = HandlerRegistry()
    # Register all built-in handlers
    PluginLoader.register_builtins(registry)
    return registry
```

---

## Key Test Cases

### `test_registry.py`

```python
def test_register_and_get():
    registry = HandlerRegistry()
    handler = DummyHandler()   # token_type = "Dummy"
    registry.register(handler)
    assert registry.get("Dummy") is handler

def test_override():
    registry = HandlerRegistry()
    registry.register(DummyHandler())
    registry.register(BetterDummyHandler())  # same token_type
    assert isinstance(registry.get("Dummy"), BetterDummyHandler)

def test_entry_points_no_plugins_installed():
    registry = HandlerRegistry()
    # Should not raise even when no plugins are installed
    registry.load_entry_points()
```

### `test_pipeline.py`

```python
def test_simple_doc_produces_pdf(simple_md, tmp_pdf, default_registry):
    cfg = Config(input_file="", output_file=str(tmp_pdf), offline=True)
    pipeline = Pipeline(cfg, default_registry)
    pipeline.run(simple_md)
    assert tmp_pdf.exists()
    assert tmp_pdf.stat().st_size > 1000  # non-trivially sized PDF

def test_mermaid_offline_uses_placeholder(diagrams_md, tmp_pdf, default_registry):
    cfg = Config(output_file=str(tmp_pdf), offline=True)
    pipeline = Pipeline(cfg, default_registry)
    pipeline.run(diagrams_md)
    assert tmp_pdf.exists()  # did not crash

def test_validate_empty_mermaid(default_registry):
    from md2pdf.core.pipeline import Pipeline
    cfg = Config(output_file="out.pdf", offline=True)
    pipeline = Pipeline(cfg, default_registry)
    issues = pipeline.validate("```mermaid\n\n```\n")
    assert any(i.code == "EMPTY_DIAGRAM" for i in issues)
```

### `test_cli.py`

```python
from typer.testing import CliRunner
from md2pdf.cli import app

runner = CliRunner()

def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Convert" in result.output

def test_missing_file():
    result = runner.invoke(app, ["nonexistent.md"])
    assert result.exit_code != 0

def test_validate_only(tmp_path, simple_md):
    src = tmp_path / "test.md"
    src.write_text(simple_md)
    result = runner.invoke(app, [str(src), "--validate-only"])
    assert result.exit_code == 0  # no errors in simple.md
```

---

## `pytest.ini` / `pyproject.toml` test config

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "network: marks tests that make real HTTP calls (deselect with -m 'not network')",
]
addopts = "-v --tb=short -m 'not network'"
```

Run network tests explicitly:
```bash
uv run pytest -m network tests/network/
```

---

## `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/

# md2pdf
.md2pdf_cache/
*.pdf

# Tools
.pytest_cache/
.coverage
htmlcov/
```

---

## README Outline

```markdown
# md2pdf — Programmatic Markdown-to-PDF Engine

Convert structured Markdown to print-ready PDFs without Pandoc, Node.js, or headless browsers.

## Features
- Standard elements: headings, paragraphs, lists, blockquotes, hyperlinks
- Multi-page tables with repeating headers
- Mermaid diagrams and LaTeX math via Kroki.io (with offline fallback + caching)
- Plugin system: add new element types, pre/post processors, and themes
- Strict layout safeguards: no ghost pages, no orphaned lines, no mid-row table splits

## Installation
\`\`\`bash
uv tool install md2pdf
\`\`\`

## Usage
\`\`\`bash
md2pdf report.md -o report.pdf
md2pdf report.md -o report.pdf --offline     # no network calls
md2pdf report.md --validate-only             # check for issues only
\`\`\`

## Plugin System
See [docs/plugin-authoring.md](docs/plugin-authoring.md).

## Configuration
See [md2pdf.toml.example](md2pdf.toml.example).
```

---

## Acceptance Criteria

- [ ] `uv run pytest` passes all unit + integration tests
- [ ] `uv run pytest -m network` passes with real Kroki connectivity
- [ ] `uv run pytest --cov=md2pdf --cov-report=term-missing` shows ≥ 80% coverage
- [ ] `uv build` produces a distributable wheel with no errors
- [ ] `README.md` exists with installation, usage, and plugin sections
- [ ] `docs/plugin-authoring.md` documents all four hook types with code examples
- [ ] `.gitignore` excludes `.md2pdf_cache/` and `*.pdf`
- [ ] No `print()` statements anywhere in `md2pdf/` package code (only `logging`)
