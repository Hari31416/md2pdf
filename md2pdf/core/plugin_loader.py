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
        from md2pdf.handlers.admonition import AdmonitionHandler
        from md2pdf.handlers.blockquote import BlockQuoteHandler
        from md2pdf.handlers.code import CodeFenceHandler
        from md2pdf.handlers.heading import HeadingHandler
        from md2pdf.handlers.latex import LatexHandler
        from md2pdf.handlers.list_ import ListHandler
        from md2pdf.handlers.mermaid import MermaidHandler
        from md2pdf.handlers.pagebreak import PageBreakHandler
        from md2pdf.handlers.paragraph import ParagraphHandler
        from md2pdf.handlers.table import TableHandler
        from md2pdf.handlers.thematic_break import ThematicBreakHandler

        def reg(handler):
            if registry.get(handler.token_type) is None:
                registry.register(handler)

        reg(HeadingHandler())
        reg(ParagraphHandler())
        reg(ListHandler())
        reg(BlockQuoteHandler())
        reg(TableHandler())
        reg(ThematicBreakHandler())
        reg(CodeFenceHandler())
        reg(AdmonitionHandler())
        reg(PageBreakHandler())
        # Register Mermaid and Latex handlers in offline mode by default
        import os

        default_cache = os.path.expanduser("~/.cache/pymd2pdf")
        reg(MermaidHandler(KrokiClient(), AssetCache(default_cache), True))
        reg(LatexHandler(KrokiClient(), AssetCache(default_cache), True))

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
        failed_plugins = []

        handlers = config_plugins.get("handlers", [])
        if isinstance(handlers, str):
            handlers = [handlers]
        for path in handlers:
            try:
                self._load_class(path, self._handlers.register)
            except Exception as e:
                logger.exception("Failed to load config plugin '%s'", path)
                failed_plugins.append((path, e))

        preprocessors = config_plugins.get("preprocessors", [])
        if isinstance(preprocessors, str):
            preprocessors = [preprocessors]
        for path in preprocessors:
            try:
                self._load_class(path, self._pre.register)
            except Exception as e:
                logger.exception("Failed to load config plugin '%s'", path)
                failed_plugins.append((path, e))

        postprocessors = config_plugins.get("postprocessors", [])
        if isinstance(postprocessors, str):
            postprocessors = [postprocessors]
        for path in postprocessors:
            try:
                self._load_class(path, self._post.register)
            except Exception as e:
                logger.exception("Failed to load config plugin '%s'", path)
                failed_plugins.append((path, e))

        if failed_plugins:
            summary = "\n".join(
                f"  - {path}: {type(err).__name__}: {err}" for path, err in failed_plugins
            )
            logger.warning(
                "Plugin loading warning: The following config plugins failed to load:\n%s", summary
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_ep_group(self, group: str, register_fn) -> None:  # type: ignore[no-untyped-def]
        failed_eps = []
        for ep in entry_points(group=group):
            try:
                cls = ep.load()
                register_fn(cls())
                logger.info("Loaded plugin '%s' from group '%s'", ep.name, group)
            except Exception as e:
                logger.exception("Failed to load plugin '%s' from group '%s'", ep.name, group)
                failed_eps.append((ep.name, e))
        if failed_eps:
            summary = "\n".join(
                f"  - {name}: {type(err).__name__}: {err}" for name, err in failed_eps
            )
            logger.warning(
                "Plugin loading warning: The following entry-point plugins in group '%s' failed to load:\n%s",
                group,
                summary,
            )

    def _load_class(self, dotted_path: str, register_fn) -> None:  # type: ignore[no-untyped-def]
        if ":" in dotted_path:
            module_path, cls_name = dotted_path.split(":", 1)
        else:
            module_path, cls_name = dotted_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, cls_name)
        register_fn(cls())
        logger.info("Loaded config plugin '%s'", dotted_path)
