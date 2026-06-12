"""HTTP client for the Kroki.io diagram-rendering API.

Kroki accepts a diagram type and source text, and returns a PNG image.

Endpoint (POST form used here to avoid URL-length limits on large diagrams)::

    POST https://kroki.io/{diagram_type}/png
    Content-Type: text/plain
    Body: <diagram source>

Supported diagram type strings used by md2pdf:

+---------------+------------------+--------------------------------------+
| Token type    | Kroki type       | Notes                                |
+===============+==================+======================================+
| ``Mermaid``   | ``"mermaid"``    | Flowcharts, sequence, Gantt, etc.    |
+---------------+------------------+--------------------------------------+
| ``LatexBlock``| ``"tikz"``       | Requires ``\\documentclass`` wrapper  |
+---------------+------------------+--------------------------------------+
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

KROKI_BASE = "https://kroki.io"


class KrokiClient:
    """Thin wrapper around the Kroki.io HTTP API.

    Args:
        base_url: Base URL of the Kroki server.  Override in tests or for
            self-hosted Kroki instances.
        timeout: Request timeout in seconds.  Defaults to ``15``.
    """

    def __init__(self, base_url: str = KROKI_BASE, timeout: int = 15) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self._session = requests.Session()

    def render(self, diagram_type: str, source: str) -> bytes:
        """Fetch PNG bytes from Kroki for the given *diagram_type* and *source*.

        Args:
            diagram_type: Kroki diagram type string (e.g. ``"mermaid"``).
            source: Raw diagram source text.

        Returns:
            Raw PNG bytes returned by the Kroki API.

        Raises:
            requests.HTTPError: If the server returns a non-2xx status code.
            requests.RequestException: On any connection/timeout error.
        """
        url = f"{self.base_url}/{diagram_type}/png"
        resp = self._session.post(
            url,
            data=source.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        logger.debug("Kroki rendered %s (%d bytes)", diagram_type, len(resp.content))
        return resp.content
