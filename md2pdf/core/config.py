"""Configuration dataclass for md2pdf."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


@dataclass
class Config:
    """Runtime configuration for the md2pdf pipeline.

    All fields map 1:1 to entries in the ``[md2pdf]`` section of
    ``md2pdf.toml``.  Unknown keys in the TOML file are silently ignored
    so that future fields can be introduced without breaking existing
    config files.

    The ``theme_config`` attribute is populated from the optional ``[theme]``
    section and is **not** a direct TOML field — it is excluded from the
    known-fields filter in :meth:`from_toml`.
    """

    input_file: str = ""
    output_file: str = "output.pdf"
    theme: str = "default"
    offline: bool = False
    cache_dir: str = ".md2pdf_cache"
    # Flat list of dotted handler class paths (e.g. "my_pkg.handlers:MyHandler").
    # Phase 5 will replace this with a structured plugins_dict sourced from [plugins].
    plugins: list[str] = field(default_factory=list)

    # Populated from the [theme] TOML section; None means "use ThemeConfig defaults".
    theme_config: Any = field(default=None, repr=False)

    @classmethod
    def from_toml(cls, path: str) -> Config:
        """Load configuration from a TOML file.

        Reads the ``[md2pdf]`` table for core settings and the ``[theme]``
        table (if present) to build a :class:`~md2pdf.styles.theme.ThemeConfig`.

        Args:
            path: Filesystem path to the TOML config file.

        Returns:
            A populated Config instance.

        Raises:
            FileNotFoundError: If *path* does not exist.
            tomllib.TOMLDecodeError: If the file is not valid TOML.
        """
        with open(path, "rb") as fh:
            data = tomllib.load(fh)

        md2pdf_section: dict = data.get("md2pdf", {})
        # ``theme_config`` is not a TOML field — exclude it from the filter.
        known: set[str] = {f.name for f in fields(cls)} - {"theme_config"}
        filtered = {k: v for k, v in md2pdf_section.items() if k in known}

        cfg = cls(**filtered)

        # Load [theme] section into a ThemeConfig (import here to avoid
        # circular imports / hard reportlab dependency at module load time).
        try:
            from md2pdf.styles.theme import ThemeConfig  # noqa: PLC0415

            theme_data: dict = data.get("theme", {})
            cfg.theme_config = ThemeConfig.from_dict(theme_data)
        except Exception:
            cfg.theme_config = None

        return cfg
