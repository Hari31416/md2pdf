"""Configuration dataclass for md2pdf."""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

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

    ``plugins_dict`` is populated from the ``[plugins]`` TOML section and
    contains three optional keys: ``handlers``, ``preprocessors``, and
    ``postprocessors``, each a list of fully-qualified class paths.
    """

    input_file: str = ""
    output_file: str = ""
    theme: str = "default"
    offline: bool = False
    cache_dir: str = os.path.expanduser("~/.cache/pymd2pdf")
    min_image_scale: float = 0.8
    toc: bool = False
    cover: bool = False
    header: str = "{title} | {section}"
    header_on_first_page: bool = False
    emoji: bool = True
    deterministic: bool = False
    page_size: str = "A4"
    orientation: str = "portrait"

    # Structured plugin config from [plugins] TOML section.
    # Keys: "handlers", "preprocessors", "postprocessors" → list[str]
    plugins_dict: dict = field(default_factory=dict)

    # Populated from the [theme] TOML section; None means "use ThemeConfig defaults".
    theme_config: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Resolve dynamic default for output_file if not specified."""
        if not self.output_file:
            if self.input_file:
                self.output_file = str(Path(self.input_file).with_suffix(".pdf"))
            else:
                self.output_file = "output.pdf"

        # Validate page size and orientation
        resolve_page_geometry(self.page_size, self.orientation)

        if self.theme_config is None:
            from md2pdf.styles.theme import PREBUILT_THEMES, ThemeConfig  # noqa: PLC0415

            if self.theme != "default" and self.theme not in PREBUILT_THEMES:
                from md2pdf.core.errors import ConfigError

                raise ConfigError(
                    f"Unknown theme: {self.theme!r}. Available themes: default, "
                    f"{', '.join(PREBUILT_THEMES.keys())}"
                )

            base_theme_data = PREBUILT_THEMES.get(self.theme, {})
            self.theme_config = ThemeConfig.from_dict(base_theme_data)

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name == "theme":
            from md2pdf.core.errors import ConfigError
            from md2pdf.styles.theme import PREBUILT_THEMES, ThemeConfig  # noqa: PLC0415

            if value != "default" and value not in PREBUILT_THEMES:
                raise ConfigError(
                    f"Unknown theme: {value!r}. Available themes: default, "
                    f"{', '.join(PREBUILT_THEMES.keys())}"
                )

            base_theme_data = PREBUILT_THEMES.get(value, {})
            super().__setattr__("theme_config", ThemeConfig.from_dict(base_theme_data))
        elif name in ("page_size", "orientation"):
            if hasattr(self, "page_size") and hasattr(self, "orientation"):
                current_size = value if name == "page_size" else self.page_size
                current_orient = value if name == "orientation" else self.orientation
                resolve_page_geometry(current_size, current_orient)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Create Config from a parsed TOML dictionary.

        Reads the ``[md2pdf]`` table for core settings, the ``[theme]``
        table (if present) to build a :class:`~md2pdf.styles.theme.ThemeConfig`,
        and the ``[plugins]`` table for plugin class paths.

        Args:
            data: A dictionary containing the parsed TOML sections.

        Returns:
            A populated Config instance.
        """
        md2pdf_section: dict = data.get("md2pdf", {})
        # ``theme_config`` and ``plugins_dict`` are not direct TOML fields.
        known: set[str] = {f.name for f in fields(cls)} - {"theme_config", "plugins_dict"}
        filtered = {k: v for k, v in md2pdf_section.items() if k in known}

        cfg = cls(**filtered)

        # Load [theme] section into a ThemeConfig (import here to avoid
        # circular imports / hard reportlab dependency at module load time).
        try:
            from dataclasses import asdict  # noqa: PLC0415

            from md2pdf.styles.theme import PREBUILT_THEMES, ThemeConfig  # noqa: PLC0415

            theme_data: dict = data.get("theme", {})
            base_dict = (
                asdict(cfg.theme_config)
                if cfg.theme_config is not None
                else dict(PREBUILT_THEMES.get(cfg.theme, {}))
            )
            merged_dict = {**base_dict, **theme_data}
            cfg.theme_config = ThemeConfig.from_dict(merged_dict)
        except Exception:
            logger.warning(
                "Failed to load [theme] section from TOML; using defaults", exc_info=True
            )

        # Load [plugins] section into plugins_dict.
        cfg.plugins_dict = data.get("plugins", {})

        return cfg

    @classmethod
    def from_toml(cls, path: str) -> Config:
        """Load configuration from a TOML file.

        Reads the ``[md2pdf]`` table for core settings, the ``[theme]``
        table (if present) to build a :class:`~md2pdf.styles.theme.ThemeConfig`,
        and the ``[plugins]`` table for plugin class paths.

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
        return cls.from_dict(data)


def resolve_page_geometry(page_size: str, orientation: str) -> tuple[float, float]:
    """Resolve page size name and orientation to a ReportLab coordinate tuple."""
    from reportlab.lib import pagesizes

    from md2pdf.core.errors import ConfigError

    orientation_clean = orientation.strip().lower()
    if orientation_clean not in ("portrait", "landscape"):
        raise ConfigError(
            f"Invalid orientation: {orientation!r}. Must be 'portrait' or 'landscape'."
        )

    size_name = page_size.strip().upper()
    matched_size = None
    for attr in dir(pagesizes):
        if attr.upper() == size_name:
            val = getattr(pagesizes, attr)
            if (
                isinstance(val, tuple)
                and len(val) == 2
                and all(isinstance(x, (int, float)) for x in val)
            ):
                matched_size = val
                break

    if matched_size is None:
        supported = []
        for attr in dir(pagesizes):
            val = getattr(pagesizes, attr)
            if (
                isinstance(val, tuple)
                and len(val) == 2
                and all(isinstance(x, (int, float)) for x in val)
            ):
                supported.append(attr)
        supported_str = ", ".join(sorted(supported))
        raise ConfigError(
            f"Unknown page size: {page_size!r}. Available page sizes: {supported_str}"
        )

    if orientation_clean == "landscape":
        return (matched_size[1], matched_size[0])
    return matched_size
