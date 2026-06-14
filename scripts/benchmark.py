#!/usr/bin/env python3
"""Rendering speed benchmarks for md2pdf, Pandoc, and Playwright.

This script detects available PDF generation engines, compiles a series of
benchmark markdown documents of varying sizes, gathers detailed timing metrics
(cold start and warm runs), and exports the results.
"""

from __future__ import annotations

import json
import logging
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any

import mistletoe

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("benchmark")

# Ensure the root of the project is in python path
ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

try:
    from md2pdf import Config, convert
except ImportError:
    logger.error("Could not import md2pdf. Ensure you are running under the project virtualenv.")
    sys.exit(1)

# Optional matplotlib import
try:
    import matplotlib.pyplot as plt

    HAS_MATPLOTLIB = True
except ImportError:
    logger.info("matplotlib not installed. Chart generation will be skipped.")
    HAS_MATPLOTLIB = False

# Optional playwright import
try:
    from playwright.sync_api import sync_playwright

    HAS_PLAYWRIGHT = True
except ImportError:
    logger.info("playwright not installed. Playwright benchmarks will be skipped.")
    HAS_PLAYWRIGHT = False


class BenchmarkRunner:
    """Orchestrates and executes rendering benchmarks across multiple engines."""

    def __init__(self, output_dir: Path, iterations: int = 5) -> None:
        self.output_dir = output_dir
        self.iterations = iterations
        self.results: dict[str, dict[str, Any]] = {}
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def detect_engines(self) -> dict[str, dict[str, Any]]:
        """Identify available CLI executables and library environments."""
        engines = {}

        # 1. md2pdf (native)
        engines["md2pdf"] = {
            "name": "md2pdf (native)",
            "available": True,
            "type": "python",
            "version": "0.5.1",
        }

        # 2. Pandoc
        pandoc_path = shutil.which("pandoc")
        if pandoc_path:
            pandoc_ver = self._get_command_version([pandoc_path, "--version"])

            # Check engines
            if shutil.which("pdflatex"):
                engines["pandoc-pdflatex"] = {
                    "name": "Pandoc (pdflatex)",
                    "available": True,
                    "type": "subprocess",
                    "cmd": [pandoc_path, "--pdf-engine=pdflatex"],
                    "version": f"Pandoc {pandoc_ver} (pdflatex)",
                }
            if shutil.which("xelatex"):
                engines["pandoc-xelatex"] = {
                    "name": "Pandoc (xelatex)",
                    "available": True,
                    "type": "subprocess",
                    "cmd": [pandoc_path, "--pdf-engine=xelatex"],
                    "version": f"Pandoc {pandoc_ver} (xelatex)",
                }
            if shutil.which("weasyprint"):
                engines["pandoc-weasyprint"] = {
                    "name": "Pandoc (weasyprint)",
                    "available": True,
                    "type": "subprocess",
                    "cmd": [pandoc_path, "--pdf-engine=weasyprint"],
                    "version": f"Pandoc {pandoc_ver} (weasyprint)",
                }

        # 3. Playwright
        if HAS_PLAYWRIGHT:
            # Test browser launchability
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch()
                    browser.close()
                engines["playwright"] = {
                    "name": "Playwright (Chromium)",
                    "available": True,
                    "type": "playwright",
                    "version": "1.60.0",
                }
            except Exception as e:
                logger.warning("Playwright is installed but browser failed to launch: %s", e)
                engines["playwright"] = {
                    "name": "Playwright (Chromium)",
                    "available": False,
                    "error": str(e),
                }
        else:
            engines["playwright"] = {
                "name": "Playwright (Chromium)",
                "available": False,
                "error": "playwright Python module not installed",
            }

        return engines

    def _get_command_version(self, cmd: list[str]) -> str:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            first_line = res.stdout.split("\n")[0]
            # typical: "pandoc 3.9.0.2" -> "3.9.0.2"
            return first_line.split()[1] if len(first_line.split()) > 1 else first_line
        except Exception:
            return "unknown"

    def run_benchmark(self, input_files: list[Path], engines: dict[str, dict[str, Any]]) -> None:
        """Run timing trials for all files and all available engines."""
        for input_file in input_files:
            file_key = input_file.name
            logger.info("=== Benchmarking document: %s ===", file_key)
            self.results[file_key] = {}
            markdown_text = input_file.read_text(encoding="utf-8")

            for engine_id, info in engines.items():
                if not info.get("available", False):
                    logger.info("  Engine '%s' is unavailable. Skipping.", info["name"])
                    continue

                logger.info("  Running %s...", info["name"])
                out_pdf = self.output_dir / f"out_{input_file.stem}_{engine_id}.pdf"

                try:
                    # COLD RUN
                    cold_time = self._measure_single_run(
                        engine_id, info, input_file, markdown_text, out_pdf, is_cold=True
                    )

                    # WARM RUNS
                    warm_times: list[float] = []
                    # For playwright, we reuse browser context across warm runs for a fair benchmark
                    if info["type"] == "playwright":
                        with sync_playwright() as p:
                            browser = p.chromium.launch()
                            for _ in range(self.iterations):
                                start = time.perf_counter()
                                html_content = mistletoe.markdown(markdown_text)
                                page = browser.new_page()
                                page.set_content(html_content)
                                page.pdf(path=str(out_pdf))
                                page.close()
                                warm_times.append(time.perf_counter() - start)
                            browser.close()
                    else:
                        for _ in range(self.iterations):
                            elapsed = self._measure_single_run(
                                engine_id, info, input_file, markdown_text, out_pdf, is_cold=False
                            )
                            warm_times.append(elapsed)

                    # Stats
                    stats = {
                        "cold_time": cold_time,
                        "warm_runs": warm_times,
                        "median": median(warm_times),
                        "mean": mean(warm_times),
                        "min": min(warm_times),
                        "max": max(warm_times),
                        "std_dev": stdev(warm_times) if len(warm_times) > 1 else 0.0,
                        "status": "Success",
                    }
                    self.results[file_key][info["name"]] = stats
                    logger.info(
                        "    Cold: %.4fs, Warm Median: %.4fs, StdDev: %.4fs",
                        stats["cold_time"],
                        stats["median"],
                        stats["std_dev"],
                    )
                except Exception as exc:
                    logger.error("    Failed to compile with %s: %s", info["name"], exc)
                    self.results[file_key][info["name"]] = {
                        "status": f"Failed: {exc}",
                        "cold_time": 0.0,
                        "median": 0.0,
                        "mean": 0.0,
                        "std_dev": 0.0,
                        "warm_runs": [],
                    }

    def _measure_single_run(
        self,
        engine_id: str,
        info: dict[str, Any],
        src_path: Path,
        markdown_text: str,
        dst_path: Path,
        is_cold: bool,
    ) -> float:
        start = time.perf_counter()

        if info["type"] == "python" and engine_id == "md2pdf":
            if is_cold:
                # Spawn a fresh Python subprocess to prevent module caching bias
                cmd = [
                    sys.executable,
                    "-c",
                    f"import sys; sys.path.insert(0, {str(ROOT)!r}); "
                    f"from md2pdf import Config, convert; "
                    f"convert({str(src_path)!r}, {str(dst_path)!r}, Config(offline=True))",
                ]
                subprocess.run(cmd, check=True, capture_output=True)
            else:
                cfg = Config(input_file=str(src_path), output_file=str(dst_path), offline=True)
                convert(str(src_path), str(dst_path), config=cfg)

        elif info["type"] == "subprocess":
            cmd = info["cmd"] + [str(src_path), "-o", str(dst_path)]
            subprocess.run(cmd, check=True, capture_output=True)

        elif info["type"] == "playwright":
            if is_cold:
                # Spawn a fresh Python subprocess to prevent playwright module caching bias
                cmd = [
                    sys.executable,
                    "-c",
                    "import mistletoe\n"
                    "from playwright.sync_api import sync_playwright\n"
                    "with sync_playwright() as p:\n"
                    "    browser = p.chromium.launch()\n"
                    "    page = browser.new_page()\n"
                    f"    page.set_content(mistletoe.markdown({markdown_text!r}))\n"
                    f"    page.pdf(path={str(dst_path)!r})\n"
                    "    browser.close()",
                ]
                subprocess.run(cmd, check=True, capture_output=True)
            else:
                with sync_playwright() as p:
                    browser = p.chromium.launch()
                    html_content = mistletoe.markdown(markdown_text)
                    page = browser.new_page()
                    page.set_content(html_content)
                    page.pdf(path=str(dst_path))
                    browser.close()

        else:
            raise ValueError(f"Unknown engine type: {info['type']}")

        return time.perf_counter() - start

    def generate_markdown_report(self, engines: dict[str, dict[str, Any]]) -> str:
        """Construct a detailed markdown table from benchmark results."""
        lines = []
        lines.append("# Rendering Performance Report")
        lines.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(
            f"**Platform:** {platform.platform()} ({platform.processor() or platform.machine()})"
        )
        lines.append(f"**Python Version:** {sys.version.split()[0]}")
        lines.append("")
        lines.append("## System Engine Versions")
        for info in engines.values():
            status = (
                "Available"
                if info.get("available", False)
                else f"Unavailable ({info.get('error', 'unknown')})"
            )
            lines.append(f"- **{info['name']}**: {info.get('version', 'N/A')} ({status})")
        lines.append("")
        lines.append("## Benchmark Summary")
        lines.append("")

        for file_name, file_results in self.results.items():
            lines.append(f"### Document: `{file_name}`")
            lines.append("")
            lines.append(
                "| Engine | Cold Start (s) | Warm Median (s) | Warm Mean (s) | Std Dev (s) | Status |"
            )
            lines.append("| :--- | :---: | :---: | :---: | :---: | :--- |")

            # Sort by warm median time
            sorted_results = sorted(
                file_results.items(),
                key=lambda x: x[1]["median"] if x[1]["status"] == "Success" else float("inf"),
            )

            for engine_name, stats in sorted_results:
                if stats["status"] == "Success":
                    lines.append(
                        f"| {engine_name} | {stats['cold_time']:.4f} | **{stats['median']:.4f}** | "
                        f"{stats['mean']:.4f} | {stats['std_dev']:.4f} | {stats['status']} |"
                    )
                else:
                    lines.append(f"| {engine_name} | - | - | - | - | {stats['status']} |")
            lines.append("")

        return "\n".join(lines)

    def generate_charts(self) -> None:
        """Create visual horizontal bar charts for both warm and cold compilation times."""
        if not HAS_MATPLOTLIB or not self.results:
            return

        # Plot Warm (Median)
        self._plot_metric(
            metric_key="median",
            error_key="std_dev",
            filename="benchmark_chart_warm.png",
            title_suffix="Warm Rendering Speed (Median)",
            x_label="Median Compilation Time (seconds, lower is better)",
        )
        # Copy to default path for backwards compatibility
        shutil.copy(
            self.output_dir / "benchmark_chart_warm.png", self.output_dir / "benchmark_chart.png"
        )

        # Plot Cold
        self._plot_metric(
            metric_key="cold_time",
            error_key=None,
            filename="benchmark_chart_cold.png",
            title_suffix="Cold Start Rendering Speed",
            x_label="Cold Start Compilation Time (seconds, lower is better)",
        )

    def _plot_metric(
        self, metric_key: str, error_key: str | None, filename: str, title_suffix: str, x_label: str
    ) -> None:
        num_files = len(self.results)
        fig, axes = plt.subplots(num_files, 1, figsize=(10, 4 * num_files), squeeze=False)
        colors = ["#3b82f6", "#64748b", "#8b5cf6", "#10b981", "#f59e0b"]

        for idx, (file_name, file_results) in enumerate(self.results.items()):
            ax = axes[idx, 0]

            # Filter successfully completed engines
            valid_results = {k: v for k, v in file_results.items() if v["status"] == "Success"}
            if not valid_results:
                ax.text(0.5, 0.5, "No successful runs", ha="center", va="center")
                ax.set_title(f"Document: {file_name}")
                continue

            sorted_engines = sorted(valid_results.items(), key=lambda x: x[1][metric_key])
            names = [x[0] for x in sorted_engines]
            values = [x[1][metric_key] for x in sorted_engines]
            xerrs = [x[1][error_key] for x in sorted_engines] if error_key else None

            bars = ax.barh(
                names,
                values,
                xerr=xerrs,
                color=colors[: len(names)],
                edgecolor="#e2e8f0",
                height=0.6,
                capsize=4,
            )

            # Styling polish
            ax.set_title(
                f"Document: {file_name} ({title_suffix})",
                fontsize=13,
                pad=15,
                fontweight="bold",
                color="#1e293b",
            )
            ax.set_xlabel(x_label, fontsize=10, labelpad=8, color="#475569")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_color("#cbd5e1")
            ax.spines["bottom"].set_color("#cbd5e1")
            ax.tick_params(colors="#475569")
            ax.grid(axis="x", linestyle="--", alpha=0.5)

            # Value labels on top of bars
            for bar in bars:
                width = bar.get_width()
                ax.text(
                    width + (max(values) * 0.01),
                    bar.get_y() + bar.get_height() / 2,
                    f" {width:.4f}s",
                    ha="left",
                    va="center",
                    fontsize=9,
                    fontweight="bold",
                    color="#1e293b",
                )

        plt.tight_layout()
        chart_path = self.output_dir / filename
        plt.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close()
        logger.info("Successfully generated performance plot: %s", chart_path)


def main() -> None:
    inputs_dir = ROOT / "scripts" / "benchmark_inputs"
    outputs_dir = ROOT / "scripts" / "benchmark_outputs"

    input_files = [
        inputs_dir / "simple.md",
        inputs_dir / "medium.md",
        inputs_dir / "large.md",
    ]

    # Verify input files exist
    for f in input_files:
        if not f.exists():
            logger.error("Input file %s does not exist. Run setup first.", f)
            sys.exit(1)

    runner = BenchmarkRunner(outputs_dir, iterations=5)

    logger.info("Detecting available engines...")
    engines = runner.detect_engines()

    logger.info("Starting benchmark trials...")
    runner.run_benchmark(input_files, engines)

    logger.info("Generating report files...")
    report_md = runner.generate_markdown_report(engines)

    # Save files
    (outputs_dir / "benchmark_results.md").write_text(report_md, encoding="utf-8")

    with open(outputs_dir / "benchmark_results.json", "w", encoding="utf-8") as jf:
        json.dump(runner.results, jf, indent=2)

    runner.generate_charts()

    # Print summary to console
    print("\n" + report_md + "\n")
    logger.info("Benchmarks completed. Results saved in: %s", outputs_dir)


if __name__ == "__main__":
    main()
