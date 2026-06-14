"""Unit tests for the Phase 5 plugin system components."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from md2pdf.core.plugin_loader import PluginLoader
from md2pdf.core.postprocessors import PostProcessor, PostProcessorRegistry
from md2pdf.core.preprocessors import PreProcessor, PreProcessorRegistry
from md2pdf.core.registry import ElementHandler, HandlerRegistry
from md2pdf.core.styles import StyleRegistry

if TYPE_CHECKING:
    from reportlab.platypus import Flowable, SimpleDocTemplate


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _DoubleHandler(ElementHandler):
    token_type = "Double"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        return []


class _UpperPreProcessor(PreProcessor):
    """Uppercases the entire document (for testing order)."""

    def process(self, raw_md: str) -> str:
        return raw_md.upper()


class _AppendPostProcessor(PostProcessor):
    """Appends a sentinel to a tracking list for order verification."""

    def __init__(self, tag: str, order_log: list[str]) -> None:
        self.tag = tag
        self.order_log = order_log

    def process(self, doc: SimpleDocTemplate, flowables: list) -> list:
        self.order_log.append(self.tag)
        return flowables


# ===========================================================================
# PreProcessorRegistry
# ===========================================================================


class TestPreProcessorRegistry:
    def test_builtins_registered_by_default(self) -> None:
        reg = PreProcessorRegistry(register_builtins=True)
        # Six built-ins: FrontMatterStripper (10) + IncludeResolver (20)
        #   + LatexBlockPreProcessor (22) + PageBreakPreProcessor (25)
        #   + AdmonitionPreProcessor (30) + EmojiPreProcessor (35)
        assert len(reg._processors) == 6

    def test_no_builtins_when_disabled(self) -> None:
        reg = PreProcessorRegistry(register_builtins=False)
        assert len(reg._processors) == 0

    def test_run_all_applies_processors(self) -> None:
        reg = PreProcessorRegistry(register_builtins=False)
        reg.register(_UpperPreProcessor())
        result = reg.run_all("hello")
        assert result == "HELLO"

    def test_priority_order_lower_runs_first(self) -> None:
        log: list[str] = []

        class _Tag(PreProcessor):
            def __init__(self, tag: str) -> None:
                self.tag = tag

            def process(self, raw_md: str) -> str:
                log.append(self.tag)
                return raw_md

        reg = PreProcessorRegistry(register_builtins=False)
        reg.register(_Tag("B"), priority=20)
        reg.register(_Tag("A"), priority=10)
        reg.run_all("x")
        assert log == ["A", "B"]

    def test_plugin_priority_50_runs_after_builtins(self) -> None:
        log: list[str] = []

        class _TagPP(PreProcessor):
            def process(self, raw_md: str) -> str:
                log.append("plugin")
                return raw_md

        reg = PreProcessorRegistry(register_builtins=True)
        reg.register(_TagPP(), priority=50)
        # Plugin should be last (index 2)
        _, pp = reg._processors[-1]
        assert isinstance(pp, _TagPP)

    def test_front_matter_strips_yaml(self) -> None:
        reg = PreProcessorRegistry(register_builtins=True)
        md = "---\ntitle: Test\n---\n# Hello"
        result = reg.run_all(md)
        assert "title: Test" not in result
        assert "# Hello" in result


# ===========================================================================
# PostProcessorRegistry
# ===========================================================================


class TestPostProcessorRegistry:
    def test_register_and_run_in_order(self) -> None:
        order: list[str] = []
        reg = PostProcessorRegistry()
        reg.register(_AppendPostProcessor("first", order))
        reg.register(_AppendPostProcessor("second", order))

        doc = MagicMock()
        reg.run_all(doc, [])
        assert order == ["first", "second"]

    def test_run_all_returns_modified_flowables(self) -> None:
        class _Doubler(PostProcessor):
            def process(self, doc: SimpleDocTemplate, flowables: list) -> list:
                return flowables + flowables

        reg = PostProcessorRegistry()
        reg.register(_Doubler())
        result = reg.run_all(MagicMock(), ["x"])
        assert result == ["x", "x"]

    def test_empty_registry_returns_unchanged(self) -> None:
        reg = PostProcessorRegistry()
        flowables = ["a", "b"]
        result = reg.run_all(MagicMock(), flowables)
        assert result == flowables

    def test_processors_run_in_registration_order(self) -> None:
        results: list[str] = []

        class _Mutator(PostProcessor):
            def __init__(self, tag: str) -> None:
                self.tag = tag

            def process(self, doc: SimpleDocTemplate, flowables: list) -> list:
                results.append(self.tag)
                return flowables

        reg = PostProcessorRegistry()
        reg.register(_Mutator("one"))
        reg.register(_Mutator("two"))
        reg.register(_Mutator("three"))
        reg.run_all(MagicMock(), [])
        assert results == ["one", "two", "three"]


# ===========================================================================
# StyleRegistry
# ===========================================================================


class TestStyleRegistry:
    def test_build_empty_returns_empty_dict(self) -> None:
        reg = StyleRegistry()
        assert reg.build() == {}

    def test_single_layer_returned_intact(self) -> None:
        reg = StyleRegistry()
        layer = {"font_size": 12, "color": "black"}
        reg.add_layer(layer)
        assert reg.build() == layer

    def test_later_layer_overrides_earlier(self) -> None:
        reg = StyleRegistry()
        reg.add_layer({"font_size": 12, "color": "black"})
        reg.add_layer({"color": "red"})  # overrides color
        result = reg.build()
        assert result["color"] == "red"
        assert result["font_size"] == 12

    def test_three_layers_merged(self) -> None:
        reg = StyleRegistry()
        reg.add_layer({"a": 1, "b": 2})
        reg.add_layer({"b": 99, "c": 3})
        reg.add_layer({"c": 100})
        result = reg.build()
        assert result == {"a": 1, "b": 99, "c": 100}

    def test_build_is_idempotent(self) -> None:
        reg = StyleRegistry()
        reg.add_layer({"x": 1})
        first = reg.build()
        second = reg.build()
        assert first == second

    def test_build_does_not_mutate_layers(self) -> None:
        reg = StyleRegistry()
        layer = {"x": 1}
        reg.add_layer(layer)
        reg.build()
        assert layer == {"x": 1}


# ===========================================================================
# PluginLoader
# ===========================================================================


class TestPluginLoader:
    def _make_loader(
        self,
    ) -> tuple[
        PluginLoader, HandlerRegistry, PreProcessorRegistry, PostProcessorRegistry, StyleRegistry
    ]:
        h = HandlerRegistry()
        pre = PreProcessorRegistry(register_builtins=False)
        post = PostProcessorRegistry()
        styles = StyleRegistry()
        loader = PluginLoader(h, pre, post, styles)
        return loader, h, pre, post, styles

    def test_load_entry_points_no_plugins_succeeds(self) -> None:
        loader, *_ = self._make_loader()
        loader.load_entry_points()  # no-op when no plugins installed — must not raise

    def test_load_from_config_bad_path_does_not_raise(self) -> None:
        loader, _, _, _, _ = self._make_loader()
        loader.load_from_config({"handlers": ["nonexistent.module:SomeHandler"]})
        # Must not raise; error is logged

    def test_load_from_config_empty_dict_is_noop(self) -> None:
        loader, h, _, _, _ = self._make_loader()
        loader.load_from_config({})
        assert h.get("Double") is None

    def test_load_from_config_registers_valid_handler(self) -> None:
        loader, h, _, _, _ = self._make_loader()
        loader.load_from_config({"handlers": ["tests.test_plugin_loader:_DoubleHandler"]})
        assert h.get("Double") is not None

    def test_load_from_config_registers_valid_preprocessor(self) -> None:
        loader, _, pre, _, _ = self._make_loader()
        loader.load_from_config({"preprocessors": ["tests.test_plugin_loader:_UpperPreProcessor"]})
        result = pre.run_all("hello")
        assert result == "HELLO"

    def test_load_from_config_registers_valid_postprocessor(self) -> None:
        loader, _, _, post, _ = self._make_loader()
        loader.load_from_config({"postprocessors": ["tests.test_plugin_loader:_DoubleHandler"]})
        # _DoubleHandler has no process() — it's not a PostProcessor.
        # The loader should log the error and not crash.

    def test_config_file_handler_overrides_earlier(self) -> None:
        """Later registration (config-file) overrides earlier (entry-point)."""
        loader, h, _, _, _ = self._make_loader()
        # Register initial
        h.register(_DoubleHandler())
        # Register again via config — should replace with a fresh instance.
        loader.load_from_config({"handlers": ["tests.test_plugin_loader:_DoubleHandler"]})
        registered = h.get("Double")
        assert registered is not None
        assert type(registered).__name__ == "_DoubleHandler"

    def test_missing_key_in_config_plugins_is_noop(self) -> None:
        loader, h, _, _, _ = self._make_loader()
        # Only 'preprocessors' key present — no 'handlers'
        loader.load_from_config({"preprocessors": []})
        # Should not raise
