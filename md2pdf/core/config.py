"""Configuration dataclass for md2pdf."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields


@dataclass
class Config:
    """Runtime configuration for the md2pdf pipeline.

    All fields map 1:1 to entries in the ``[md2pdf]`` section of
    ``md2pdf.toml``.  Unknown keys in the TOML file are silently ignored
    so that future fields can be introduced without breaking existing
    config files.

    Note:
        ``theme_config`` (ThemeConfig dataclass) will be added in Phase 3.
        ``plugins_dict`` (structured plugin config) will be added in Phase 5.
    """

    input_file: str = ""
    output_file: str = "output.pdf"
    theme: str = "default"
    offline: bool = False
    cache_dir: str = ".md2pdf_cache"
    # Flat list of dotted handler class paths (e.g. "my_pkg.handlers:MyHandler").
    # Phase 5 will replace this with a structured plugins_dict sourced from [plugins].
    plugins: list[str] = field(default_factory=list)

    @classmethod
    def from_toml(cls, path: str) -> Config:
        """Load configuration from a TOML file.

        Only the ``[md2pdf]`` table is read; other tables (e.g. ``[theme]``,
        ``[plugins]``) are reserved for Phase 3 / Phase 5 and ignored here.

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
        known: set[str] = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in md2pdf_section.items() if k in known}
        return cls(**filtered)
