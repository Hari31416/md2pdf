"""Shared pytest fixtures for the md2pdf test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from md2pdf.core.config import Config
from md2pdf.core.plugin_loader import PluginLoader
from md2pdf.core.registry import HandlerRegistry

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def empty_registry() -> HandlerRegistry:
    """A fresh HandlerRegistry with no handlers registered."""
    return HandlerRegistry()


@pytest.fixture
def default_config(tmp_path) -> Config:
    """A Config instance pointing output to a temp directory."""
    return Config(
        input_file="",
        output_file=str(tmp_path / "output.pdf"),
    )


@pytest.fixture
def simple_md() -> str:
    """Read and return simple.md fixture content."""
    return (FIXTURES / "simple.md").read_text(encoding="utf-8")


@pytest.fixture
def tmp_pdf(tmp_path) -> Path:
    """Path to a temporary PDF file."""
    return tmp_path / "output.pdf"


@pytest.fixture
def default_registry() -> HandlerRegistry:
    """A HandlerRegistry with all built-in handlers registered."""
    registry = HandlerRegistry()
    PluginLoader.register_builtins(registry)
    return registry
