"""Shared pytest fixtures for the md2pdf test suite."""

from __future__ import annotations

import pytest

from md2pdf.core.config import Config
from md2pdf.core.registry import HandlerRegistry


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
