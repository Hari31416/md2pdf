# Phase 1: Project Foundation

**Goal:** Establish the project skeleton, tooling, package structure, and the plugin registry core so every subsequent phase builds on a stable base.

---

## Deliverables

- `pyproject.toml` — uv-managed package with entry-point group declaration
- `md2pdf/` — top-level package with sub-packages wired up
- `md2pdf/core/registry.py` — `ElementHandler` ABC + `HandlerRegistry`
- `md2pdf/core/pipeline.py` — skeleton `Pipeline` class (stages as no-ops)
- `md2pdf/core/config.py` — `Config` dataclass (parsed from `md2pdf.toml`)
- `md2pdf/cli.py` — thin CLI entry point (argparse / typer)
- `md2pdf/__init__.py` — public API surface (`convert(src, dst, config)`)
- `tests/` — pytest skeleton + `conftest.py`
- `.md2pdf_cache/` — gitignored cache dir placeholder

---

## Directory Layout (target)

```
md2pdf/
├── pyproject.toml
├── md2pdf.toml.example          # sample user config
├── md2pdf/
│   ├── __init__.py
│   ├── cli.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── pipeline.py
│   │   └── registry.py
│   └── handlers/               # empty, filled in Phase 3
│       └── __init__.py
└── tests/
    ├── conftest.py
    └── test_registry.py
```

---

## Implementation Notes

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "md2pdf"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "reportlab>=4.0",
    "mistletoe>=1.3",
    "beautifulsoup4>=4.12",
    "requests>=2.31",
    "typer>=0.12",
    "tomli>=2.0; python_version < '3.11'",
]

[project.scripts]
md2pdf = "md2pdf.cli:app"

[project.entry-points."md2pdf.handlers"]
# built-in handlers declared here (Phase 3)
# third-party plugins declare their own entries in their own pyproject.toml

[dependency-groups]
dev = ["pytest>=8", "pytest-cov"]
```

### `ElementHandler` ABC (`registry.py`)

```python
from abc import ABC, abstractmethod
from reportlab.platypus import Flowable

class ElementHandler(ABC):
    token_type: str  # claimed token/node type name

    @abstractmethod
    def render(self, token: dict, styles: dict) -> list[Flowable]:
        """Convert a parsed AST token into ReportLab flowables."""
        ...

    def can_handle(self, token: dict) -> bool:
        """Override for conditional dispatch (default: match token_type)."""
        return token.get("type") == self.token_type
```

### `HandlerRegistry`

```python
class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ElementHandler] = {}

    def register(self, handler: ElementHandler) -> None:
        self._handlers[handler.token_type] = handler

    def get(self, token_type: str) -> ElementHandler | None:
        return self._handlers.get(token_type)

    def load_entry_points(self) -> None:
        """Discover and register handlers from installed plugins."""
        from importlib.metadata import entry_points
        for ep in entry_points(group="md2pdf.handlers"):
            handler_cls = ep.load()
            self.register(handler_cls())

    def load_from_config(self, dotted_paths: list[str]) -> None:
        """Instantiate and register handlers from config-declared class paths."""
        import importlib
        for path in dotted_paths:
            module_path, cls_name = path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            handler_cls = getattr(module, cls_name)
            self.register(handler_cls())
```

### `Config` dataclass (`config.py`)

```python
from dataclasses import dataclass, field

@dataclass
class Config:
    input_file: str = ""
    output_file: str = "output.pdf"
    theme: str = "default"
    offline: bool = False
    cache_dir: str = ".md2pdf_cache"
    plugins: list[str] = field(default_factory=list)  # dotted class paths

    @classmethod
    def from_toml(cls, path: str) -> "Config":
        import tomllib
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(**data.get("md2pdf", {}))
```

### `Pipeline` skeleton (`pipeline.py`)

```python
class Pipeline:
    def __init__(self, config: Config, registry: HandlerRegistry) -> None:
        self.config = config
        self.registry = registry

    def run(self, raw_md: str) -> None:
        md = self._pre_process(raw_md)      # Phase 2 / plugin hook
        tokens = self._parse(md)            # Phase 2
        flowables = self._map(tokens)       # Phase 3
        self._render(flowables)             # Phase 4 / Phase 7

    def _pre_process(self, raw_md: str) -> str:
        return raw_md   # placeholder

    def _parse(self, md: str) -> list[dict]:
        return []       # placeholder

    def _map(self, tokens: list[dict]) -> list:
        return []       # placeholder

    def _render(self, flowables: list) -> None:
        pass            # placeholder
```

### CLI (`cli.py`)

```python
import typer
app = typer.Typer()

@app.command()
def convert(
    input: str = typer.Argument(..., help="Path to input .md file"),
    output: str = typer.Option("output.pdf", "-o", help="Output PDF path"),
    config: str = typer.Option(None, "-c", help="Path to md2pdf.toml"),
    theme: str = typer.Option("default", "-t", help="Theme name"),
    offline: bool = typer.Option(False, "--offline", help="Skip Kroki API calls"),
):
    ...  # wire up Config + Pipeline in Phase 2
```

---

## Acceptance Criteria

- [ ] `uv sync` installs all dependencies cleanly
- [ ] `md2pdf --help` prints usage without error
- [ ] `pytest tests/` passes (registry unit tests: register, get, duplicate override)
- [ ] `HandlerRegistry.load_entry_points()` runs without error (no plugins installed = no-op)
- [ ] `Config.from_toml()` round-trips the example config correctly
