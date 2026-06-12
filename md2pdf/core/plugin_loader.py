"""PluginLoader — wires both plugin discovery mechanisms to all four registries.

Two discovery mechanisms are supported:

1. **Entry-point discovery** (:meth:`load_entry_points`): auto-discovers
   installed Python packages that advertise handlers, pre-processors,
   post-processors, or stylesheet overrides via ``pyproject.toml``
   entry-point groups.

2. **Config-file discovery** (:meth:`load_from_config`): loads plugin classes
   declared in the ``[plugins]`` section of ``md2pdf.toml``.

All loading errors are caught, logged, and skipped so that one bad plugin
never aborts a conversion run.
"""

from __future__ import annotations

import importlib
import logging
from importlib.metadata import entry_points

from md2pdf.core.postprocessors import PostProcessorRegistry
from md2pdf.core.preprocessors import PreProcessorRegistry
from md2pdf.core.registry import HandlerRegistry
from md2pdf.core.styles import StyleRegistry

logger = logging.getLogger(__name__)


class PluginLoader:
    """Loads and registers plugins into all four hook-stage registries.

    Args:
        handler_registry: Registry for :class:`~md2pdf.core.registry.ElementHandler` plugins.
        pre_registry: Registry for :class:`~md2pdf.core.preprocessors.PreProcessor` plugins.
        post_registry: Registry for :class:`~md2pdf.core.postprocessors.PostProcessor` plugins.
        style_registry: Registry for stylesheet-override plugins.
    """

    def __init__(
        self,
        handler_registry: HandlerRegistry,
        pre_registry: PreProcessorRegistry,
        post_registry: PostProcessorRegistry,
        style_registry: StyleRegistry,
    ) -> None:
        self._handlers = handler_registry
        self._pre = pre_registry
        self._post = post_registry
        self._styles = style_registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def register_builtins(registry: HandlerRegistry) -> None:
        """Register all built-in handlers directly into a HandlerRegistry.

        This is useful for tests or standalone usage where setup.py / pyproject.toml
        entry points are not installed in the current environment.
        """
        from md2pdf.assets.cache import AssetCache
        from md2pdf.assets.kroki import KrokiClient
        from md2pdf.handlers.blockquote import BlockQuoteHandler
        from md2pdf.handlers.code import CodeFenceHandler
        from md2pdf.handlers.heading import HeadingHandler
        from md2pdf.handlers.latex import LatexHandler
        from md2pdf.handlers.list_ import ListHandler
        from md2pdf.handlers.mermaid import MermaidHandler
        from md2pdf.handlers.paragraph import ParagraphHandler
        from md2pdf.handlers.table import TableHandler
        from md2pdf.handlers.thematic_break import ThematicBreakHandler

        registry.register(HeadingHandler())
        registry.register(ParagraphHandler())
        registry.register(ListHandler())
        registry.register(BlockQuoteHandler())
        registry.register(TableHandler())
        registry.register(ThematicBreakHandler())
        registry.register(CodeFenceHandler())
        # Register Mermaid and Latex handlers in offline mode by default
        import os

        default_cache = os.path.expanduser("~/.cache/pymd2pdf")
        registry.register(MermaidHandler(KrokiClient(), AssetCache(default_cache), True))
        registry.register(LatexHandler(KrokiClient(), AssetCache(default_cache), True))

    def load_entry_points(self) -> None:
        """Auto-discover installed packages that declare ``md2pdf.*`` entry points.

        Entry-point groups processed:

        - ``md2pdf.handlers``      → :class:`~md2pdf.core.registry.ElementHandler` subclass
        - ``md2pdf.preprocessors`` → :class:`~md2pdf.core.preprocessors.PreProcessor` subclass
        - ``md2pdf.postprocessors``→ :class:`~md2pdf.core.postprocessors.PostProcessor` subclass
        - ``md2pdf.stylesheets``   → class with ``get_stylesheet() -> dict``

        One bad entry point never prevents others from loading.
        """
        self._load_ep_group("md2pdf.handlers", self._handlers.register)
        self._load_ep_group("md2pdf.preprocessors", self._pre.register)
        self._load_ep_group("md2pdf.postprocessors", self._post.register)
        self._load_ep_group(
            "md2pdf.stylesheets",
            lambda obj: self._styles.add_layer(obj.get_stylesheet()),
        )

    def load_from_config(self, config_plugins: dict) -> None:
        """Load plugins declared in the ``[plugins]`` section of ``md2pdf.toml``.

        Expected *config_plugins* structure::

            {
                "handlers":      ["my_pkg.handlers:MyHandler"],
                "preprocessors": ["my_pkg.preprocessors:MyPP"],
                "postprocessors":["my_pkg.postprocessors:MyPost"],
            }

        Args:
            config_plugins: Dict sourced from the ``[plugins]`` TOML section.
                Missing keys are silently ignored.
        """
        for path in config_plugins.get("handlers", []):
            self._load_class(path, self._handlers.register)
        for path in config_plugins.get("preprocessors", []):
            self._load_class(path, self._pre.register)
        for path in config_plugins.get("postprocessors", []):
            self._load_class(path, self._post.register)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_ep_group(self, group: str, register_fn) -> None:  # type: ignore[no-untyped-def]
        for ep in entry_points(group=group):
            try:
                cls = ep.load()
                register_fn(cls())
                logger.info("Loaded plugin '%s' from group '%s'", ep.name, group)
            except Exception:
                logger.exception("Failed to load plugin '%s' from group '%s'", ep.name, group)

    def _load_class(self, dotted_path: str, register_fn) -> None:  # type: ignore[no-untyped-def]
        try:
            if ":" in dotted_path:
                module_path, cls_name = dotted_path.split(":", 1)
            else:
                module_path, cls_name = dotted_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            cls = getattr(module, cls_name)
            register_fn(cls())
            logger.info("Loaded config plugin '%s'", dotted_path)
        except Exception:
            logger.exception("Failed to load config plugin '%s'", dotted_path)
