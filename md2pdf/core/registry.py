"""ElementHandler ABC and HandlerRegistry for the md2pdf plugin system."""

from __future__ import annotations

import importlib
import logging
from abc import ABC, abstractmethod
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reportlab.platypus import Flowable

logger = logging.getLogger(__name__)


class ElementHandler(ABC):
    """Base class for all element handlers.

    Subclasses must set ``token_type`` to the token type string they claim
    (e.g. ``"Heading"``, ``"Table"``), and implement ``render()``.

    Third-party plugins subclass this and declare themselves under the
    ``md2pdf.handlers`` entry-point group.
    """

    #: The token type this handler claims.  Must be set on the subclass.
    token_type: str

    @abstractmethod
    def render(self, token: dict, styles: dict) -> list[Flowable]:
        """Convert a parsed AST token into a list of ReportLab flowables.

        Args:
            token: Normalised token dict produced by the parser.
            styles: Merged stylesheet dict built from ThemeConfig (Phase 3).

        Returns:
            A (possibly empty) list of ReportLab ``Flowable`` instances.
        """
        ...

    def can_handle(self, token: dict) -> bool:
        """Return True if this handler should process *token*.

        Override for conditional dispatch (e.g. a handler that only handles
        level-1 headings).  The default implementation matches on
        ``token["type"] == self.token_type``.
        """
        return token.get("type") == self.token_type


class HandlerRegistry:
    """Registry that maps token type strings to ElementHandler instances.

    Registration is last-writer-wins: registering a handler for a token type
    that already has one replaces the previous handler.  This allows plugins
    to override built-in handlers cleanly.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ElementHandler] = {}

    def register(self, handler: ElementHandler) -> None:
        """Register *handler*.  Replaces any existing handler for the same token type."""
        self._handlers[handler.token_type] = handler
        logger.debug(
            "Registered handler for token type '%s': %s", handler.token_type, type(handler).__name__
        )

    def get(self, token_type: str) -> ElementHandler | None:
        """Return the handler registered for *token_type*, or ``None``."""
        return self._handlers.get(token_type)

    def load_entry_points(self) -> None:
        """Auto-discover and register handlers from installed packages.

        Packages advertise handlers under the ``md2pdf.handlers`` entry-point
        group in their ``pyproject.toml``::

            [project.entry-points."md2pdf.handlers"]
            MyToken = "my_package.handlers:MyHandler"

        Errors loading individual plugins are logged and skipped so one bad
        plugin never aborts the process.
        """
        for ep in entry_points(group="md2pdf.handlers"):
            try:
                handler_cls = ep.load()
                self.register(handler_cls())
                logger.info("Loaded entry-point handler plugin '%s'", ep.name)
            except Exception:
                logger.exception("Failed to load entry-point handler plugin '%s'", ep.name)

    def load_from_config(self, dotted_paths: list[str] | str) -> None:
        """Instantiate and register handlers from config-declared class paths.

        Each entry in *dotted_paths* must be a fully-qualified Python class
        path, e.g. ``"my_package.handlers:MyHandler"``.

        Errors are logged and skipped — they do not raise.
        """
        if isinstance(dotted_paths, str):
            dotted_paths = [dotted_paths]

        failed_plugins = []
        for path in dotted_paths:
            try:
                if ":" in path:
                    module_path, cls_name = path.split(":", 1)
                else:
                    module_path, cls_name = path.rsplit(".", 1)
                module = importlib.import_module(module_path)
                handler_cls = getattr(module, cls_name)
                self.register(handler_cls())
            except Exception as e:
                logger.exception("Failed to load handler from config path '%s'", path)
                failed_plugins.append((path, e))

        if failed_plugins:
            summary = "\n".join(
                f"  - {path}: {type(err).__name__}: {err}" for path, err in failed_plugins
            )
            logger.warning(
                "Plugin loading warning: The following handlers failed to load:\n%s", summary
            )
