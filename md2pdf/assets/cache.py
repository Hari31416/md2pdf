"""Disk-based asset cache for rendered diagram images.

Cache key is SHA-256(``{diagram_type}:{source_text}``), stored as
``{cache_dir}/{key}.png``.  Because the key is derived from the content,
changing the source automatically produces a new key — no explicit
invalidation is needed.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AssetCache:
    """Hash-keyed disk cache for PNG diagram images.

    Args:
        cache_dir: Directory to store cached PNG files.  Created on first use
            if it does not already exist.  Defaults to ``.md2pdf_cache``.
    """

    def __init__(self, cache_dir: str = ".md2pdf_cache") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, diagram_type: str, source: str) -> bytes | None:
        """Return cached PNG bytes, or ``None`` if not cached.

        Args:
            diagram_type: Kroki diagram type string (e.g. ``"mermaid"``).
            source: Raw diagram source text.

        Returns:
            PNG bytes if the entry exists in the cache, otherwise ``None``.
        """
        path = self._path(diagram_type, source)
        if path.exists():
            logger.debug("Cache hit: %s", path.name)
            return path.read_bytes()
        logger.debug("Cache miss: %s", path.name)
        return None

    def put(self, diagram_type: str, source: str, data: bytes) -> None:
        """Store *data* in the cache under the key for (*diagram_type*, *source*).

        Args:
            diagram_type: Kroki diagram type string.
            source: Raw diagram source text.
            data: PNG bytes to cache.
        """
        import os
        import tempfile

        path = self._path(diagram_type, source)
        # Write to temporary file in the same cache directory to ensure atomic rename
        with tempfile.NamedTemporaryFile(dir=self.cache_dir, suffix=".tmp", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        try:
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
        logger.debug("Cached %d bytes → %s", len(data), path.name)

    def path_for(self, diagram_type: str, source: str) -> Path:
        """Return the filesystem Path where the cached image is (or would be) stored.

        Args:
            diagram_type: Kroki diagram type string.
            source: Raw diagram source text.

        Returns:
            The Path object representing the location of the cached file.
        """
        return self._path(diagram_type, source)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key(self, diagram_type: str, source: str) -> str:
        raw = f"{diagram_type}:{source}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _path(self, diagram_type: str, source: str) -> Path:
        return self.cache_dir / f"{self._key(diagram_type, source)}.png"
