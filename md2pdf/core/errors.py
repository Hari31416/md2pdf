"""Structured error and validation issue types for md2pdf."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class ValidationIssue:
    """Represents a warning or error discovered during pre-render validation."""

    severity: Literal["error", "warning"]
    code: str  # e.g. "UNSUPPORTED_ELEMENT", "EMPTY_TABLE", "NESTED_TABLE"
    message: str
    line: int | None = None
    element_type: str | None = None


class Md2PdfError(Exception):
    """Base exception for all md2pdf errors."""


class ParseError(Md2PdfError):
    """Raised when the markdown cannot be parsed."""


class RenderError(Md2PdfError):
    """Raised when PDF generation fails."""


class ConfigError(Md2PdfError):
    """Raised for invalid configuration."""
