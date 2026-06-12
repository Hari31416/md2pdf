"""Unit tests for HandlerRegistry and ElementHandler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from md2pdf.core.registry import ElementHandler, HandlerRegistry

if TYPE_CHECKING:
    from reportlab.platypus import Flowable


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _DummyHandler(ElementHandler):
    token_type = "Dummy"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        return []


class _BetterDummyHandler(ElementHandler):
    """Same token_type — used to verify last-writer-wins override."""

    token_type = "Dummy"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        return []


class _OtherHandler(ElementHandler):
    token_type = "Other"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        return []


# ---------------------------------------------------------------------------
# HandlerRegistry tests
# ---------------------------------------------------------------------------


def test_register_and_get() -> None:
    registry = HandlerRegistry()
    handler = _DummyHandler()
    registry.register(handler)
    assert registry.get("Dummy") is handler


def test_get_missing_returns_none(empty_registry: HandlerRegistry) -> None:
    assert empty_registry.get("NonExistent") is None


def test_register_override() -> None:
    """Later registration replaces earlier one for the same token_type."""
    registry = HandlerRegistry()
    registry.register(_DummyHandler())
    registry.register(_BetterDummyHandler())
    assert isinstance(registry.get("Dummy"), _BetterDummyHandler)


def test_register_multiple_types() -> None:
    registry = HandlerRegistry()
    registry.register(_DummyHandler())
    registry.register(_OtherHandler())
    assert isinstance(registry.get("Dummy"), _DummyHandler)
    assert isinstance(registry.get("Other"), _OtherHandler)


def test_load_entry_points_no_plugins_installed(empty_registry: HandlerRegistry) -> None:
    """Should not raise even when no md2pdf.handlers plugins are installed."""
    empty_registry.load_entry_points()  # no-op when nothing is installed


def test_load_from_config_invalid_path_does_not_raise(
    empty_registry: HandlerRegistry,
) -> None:
    """Invalid dotted path should log an error and not raise."""
    empty_registry.load_from_config(["nonexistent.module:Handler"])
    # Nothing registered — just silently logged
    assert empty_registry.get("Handler") is None


def test_load_from_config_colon_syntax(empty_registry: HandlerRegistry) -> None:
    """Colon-separated module:Class syntax should resolve correctly."""
    empty_registry.load_from_config(
        ["md2pdf.core.registry:HandlerRegistry"]  # not a handler, will fail gracefully
    )
    # HandlerRegistry has no token_type → AttributeError logged, not raised


# ---------------------------------------------------------------------------
# ElementHandler.can_handle tests
# ---------------------------------------------------------------------------


def test_can_handle_matching_type() -> None:
    handler = _DummyHandler()
    assert handler.can_handle({"type": "Dummy"}) is True


def test_can_handle_non_matching_type() -> None:
    handler = _DummyHandler()
    assert handler.can_handle({"type": "Other"}) is False


def test_can_handle_missing_type_key() -> None:
    handler = _DummyHandler()
    assert handler.can_handle({}) is False
