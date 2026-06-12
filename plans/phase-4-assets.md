# Phase 4: Asset Compilation (Kroki API + Caching + Offline Fallback)

**Goal:** Implement remote rendering of LaTeX and Mermaid blocks via the Kroki.io API, with disk-based caching and a graceful offline fallback so network outages never crash a run.

**Depends on:** Phase 2 (token types `Mermaid`, `LatexBlock`), Phase 3 (handler pattern)

---

## Deliverables

- `md2pdf/assets/kroki.py` — `KrokiClient` (HTTP client + cache logic)
- `md2pdf/assets/cache.py` — `AssetCache` (hash-keyed disk cache)
- `md2pdf/assets/fallback.py` — `FallbackRenderer` (placeholder box flowable)
- `md2pdf/handlers/mermaid.py` — `MermaidHandler`
- `md2pdf/handlers/latex.py` — `LatexHandler`
- `tests/test_assets.py` — unit tests with mocked HTTP

---

## Kroki API Integration (`kroki.py`)

Kroki.io accepts a diagram type + source, and returns a PNG (or SVG).

**Endpoint pattern:**
```
POST https://kroki.io/{diagram_type}/png
Body: plain text of the diagram source
```

Or alternatively the GET form with base64-encoded source:
```
GET https://kroki.io/{diagram_type}/png/{base64url_source}
```

We use the POST form to avoid URL length limits on large diagrams.

```python
import requests
import logging

KROKI_BASE = "https://kroki.io"

class KrokiClient:
    def __init__(self, base_url: str = KROKI_BASE, timeout: int = 15) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self._session = requests.Session()

    def render(self, diagram_type: str, source: str) -> bytes:
        """Fetch PNG bytes from Kroki. Raises requests.HTTPError on failure."""
        url = f"{self.base_url}/{diagram_type}/png"
        resp = self._session.post(
            url,
            data=source.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        logging.debug("Kroki rendered %s (%d bytes)", diagram_type, len(resp.content))
        return resp.content
```

Supported diagram type strings:
| Token type | Kroki type |
|-----------|------------|
| `Mermaid` | `"mermaid"` |
| `LatexBlock` | `"blockdiag"` — **No.** For LaTeX use `"plantuml"` with `@startmath` ... or better: use `"latex"` via Kroki's `tikz` endpoint |

> **Note on LaTeX:** Kroki supports `tikz` and `bytefield` but not raw LaTeX math. Best approach: render LaTeX math blocks using `mermaid`'s `$$` support OR use the **Mermaid.ink** API specifically for math. Document clearly which syntax is supported. Phase 4 should verify and document the exact Kroki endpoint for math.

Recommended final mapping:
- `LatexBlock` → Kroki `"tikz"` for block math (requires `\begin{document}` wrapper)
- `Mermaid` → Kroki `"mermaid"`

---

## Disk Cache (`cache.py`)

Cache key = `sha256(diagram_type + ":" + source_text)` → stored as `{cache_dir}/{key}.png`

```python
import hashlib
from pathlib import Path

class AssetCache:
    def __init__(self, cache_dir: str = ".md2pdf_cache") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key(self, diagram_type: str, source: str) -> str:
        raw = f"{diagram_type}:{source}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, diagram_type: str, source: str) -> bytes | None:
        path = self.cache_dir / f"{self._key(diagram_type, source)}.png"
        if path.exists():
            logging.debug("Cache hit: %s", path.name)
            return path.read_bytes()
        return None

    def put(self, diagram_type: str, source: str, data: bytes) -> None:
        path = self.cache_dir / f"{self._key(diagram_type, source)}.png"
        path.write_bytes(data)
        logging.debug("Cached: %s", path.name)
```

Cache invalidation: none — hash-keyed, so changed source = new key automatically.

---

## Offline Fallback (`fallback.py`)

When `Config.offline=True` or a network error occurs, render a styled placeholder box instead of crashing.

```python
from reportlab.platypus import Flowable
from reportlab.lib import colors
from reportlab.lib.units import mm

class PlaceholderBox(Flowable):
    """A grey bordered box showing diagram type and source preview."""

    def __init__(self, diagram_type: str, source: str,
                 width: float = 400, height: float = 80) -> None:
        super().__init__()
        self.diagram_type = diagram_type
        self.source_preview = source[:120] + ("..." if len(source) > 120 else "")
        self.width = width
        self.height = height

    def draw(self) -> None:
        c = self.canv
        c.setStrokeColor(colors.HexColor("#aaaaaa"))
        c.setFillColor(colors.HexColor("#f9f9f9"))
        c.rect(0, 0, self.width, self.height, fill=1)
        c.setFillColor(colors.HexColor("#888888"))
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(6, self.height - 14,
                     f"[{self.diagram_type} diagram — offline / render failed]")
        c.setFont("Courier", 7)
        c.drawString(6, self.height - 28, self.source_preview)
```

---

## `MermaidHandler` and `LatexHandler`

Both follow the same pattern:

```python
from reportlab.platypus import Image
from io import BytesIO

class MermaidHandler(ElementHandler):
    token_type = "Mermaid"

    def __init__(self, client: KrokiClient, cache: AssetCache,
                 offline: bool = False) -> None:
        self.client = client
        self.cache = cache
        self.offline = offline

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        source = token["raw"]
        diagram_type = "mermaid"

        if self.offline:
            return [PlaceholderBox(diagram_type, source)]

        png = self.cache.get(diagram_type, source)
        if png is None:
            try:
                png = self.client.render(diagram_type, source)
                self.cache.put(diagram_type, source, png)
            except Exception as exc:
                logging.warning("Kroki render failed (%s): %s", diagram_type, exc)
                return [PlaceholderBox(diagram_type, source)]

        img = Image(BytesIO(png), width=400, height=None)  # height=None → keep aspect
        img.hAlign = "CENTER"
        return [img]
```

`LatexHandler` is identical but `diagram_type = "tikz"` and source wrapping:

```python
def _wrap_latex(source: str) -> str:
    return (
        r"\documentclass{standalone}"
        r"\usepackage{amsmath}"
        r"\begin{document}"
        f"${source}$"
        r"\end{document}"
    )
```

---

## Dependency Injection in Pipeline

`MermaidHandler` and `LatexHandler` need `KrokiClient` and `AssetCache`. The `Pipeline` constructs and injects them:

```python
class Pipeline:
    def __init__(self, config: Config, registry: HandlerRegistry) -> None:
        ...
        cache = AssetCache(config.cache_dir)
        client = KrokiClient()
        registry.register(MermaidHandler(client, cache, config.offline))
        registry.register(LatexHandler(client, cache, config.offline))
```

---

## Acceptance Criteria

- [ ] `AssetCache.get()` returns `None` on first call, cached bytes on second (no network on second)
- [ ] `MermaidHandler` returns `PlaceholderBox` when `offline=True`
- [ ] `MermaidHandler` returns `PlaceholderBox` (not exception) when Kroki returns HTTP 5xx
- [ ] Rendering the same source twice makes exactly 1 HTTP call (cache verified via mock)
- [ ] Integration test: real Kroki call for a trivial `graph TD; A-->B;` returns a valid PNG (skipped in CI with `pytest.mark.network`)
- [ ] `.md2pdf_cache/` is listed in `.gitignore`
