"""Automation script to compile all documentation and examples to PDF."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("build_docs")

# Ensure the root of the project is in python path
ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

try:
    from md2pdf import Config, convert
except ImportError:
    logger.error(
        "Could not import md2pdf. Please run the script in the environment (e.g., using uv run)."
    )
    sys.exit(1)


def build_docs() -> None:
    """Compile documentation files in docs/ to PDFs."""
    docs_to_compile = [
        ("docs/user_manual.md", "docs/user_manual.pdf", Config(toc=True, deterministic=True)),
    ]

    logger.info("--- Compiling Documentation Suite ---")
    for src_rel, dst_rel, config in docs_to_compile:
        src = ROOT / src_rel
        dst = ROOT / dst_rel
        if not src.exists():
            logger.warning("Source documentation file %s does not exist.", src_rel)
            continue
        logger.info("Compiling %s -> %s...", src_rel, dst_rel)
        try:
            convert(str(src), str(dst), config=config)
            logger.info("Successfully wrote %s", dst_rel)
        except Exception as exc:
            logger.error("Failed to compile %s: %s", src_rel, exc, exc_info=True)


def build_examples() -> None:
    """Compile examples in examples/ to PDFs using local configuration overrides."""
    examples_dir = ROOT / "examples"
    if not examples_dir.exists():
        logger.warning("Examples directory does not exist.")
        return

    logger.info("--- Compiling Examples Suite ---")
    for item in examples_dir.iterdir():
        if not item.is_dir():
            continue

        md_files = list(item.glob("*.md"))
        if not md_files:
            logger.warning("No Markdown file found in example directory %s.", item.name)
            continue

        # Assume the first markdown file is the primary document
        src = md_files[0]
        toml_path = item / "md2pdf.toml"
        dst = src.with_suffix(".pdf")

        dst_rel = os.path.relpath(dst, ROOT)

        logger.info("Compiling example %s...", item.name)

        config = Config(deterministic=True)
        if toml_path.exists():
            toml_rel = os.path.relpath(toml_path, ROOT)
            logger.info("  Loading config from %s", toml_rel)
            try:
                config = Config.from_toml(str(toml_path))
                config.deterministic = True
            except Exception as exc:
                logger.error("  Failed to load config %s: %s", toml_rel, exc)

        try:
            convert(str(src), str(dst), config=config)
            logger.info("Successfully wrote %s", dst_rel)
        except Exception as exc:
            logger.error("Failed to compile example %s: %s", item.name, exc, exc_info=True)


if __name__ == "__main__":
    build_docs()
    build_examples()
    logger.info("--- Build Complete ---")
