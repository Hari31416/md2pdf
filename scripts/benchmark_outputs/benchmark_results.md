# Rendering Performance Report
**Date:** 2026-06-14 23:12:46
**Platform:** macOS-26.5.1-arm64-arm-64bit-Mach-O (arm)
**Python Version:** 3.13.5

## System Engine Versions
- **md2pdf (native)**: 0.5.1 (Available)
- **Pandoc (pdflatex)**: Pandoc 3.9.0.2 (pdflatex) (Available)
- **Pandoc (xelatex)**: Pandoc 3.9.0.2 (xelatex) (Available)
- **Pandoc (weasyprint)**: Pandoc 3.9.0.2 (weasyprint) (Available)
- **Playwright (Chromium)**: 1.60.0 (Available)

## Benchmark Summary

### Document: `simple.md`

| Engine | Cold Start (s) | Warm Median (s) | Warm Mean (s) | Std Dev (s) | Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| md2pdf (native) | 0.2532 | **0.0143** | 0.0182 | 0.0095 | Success |
| Playwright (Chromium) | 0.3873 | **0.0405** | 0.0426 | 0.0036 | Success |
| Pandoc (weasyprint) | 0.3621 | **0.3695** | 0.3735 | 0.0162 | Success |
| Pandoc (pdflatex) | 0.7609 | **0.7838** | 0.7839 | 0.0177 | Success |
| Pandoc (xelatex) | 1.4801 | **1.4980** | 1.5025 | 0.0230 | Success |

### Document: `medium.md`

| Engine | Cold Start (s) | Warm Median (s) | Warm Mean (s) | Std Dev (s) | Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| Playwright (Chromium) | 0.4109 | **0.0438** | 0.0455 | 0.0038 | Success |
| md2pdf (native) | 0.4724 | **0.0461** | 0.0692 | 0.0475 | Success |
| Pandoc (weasyprint) | 0.4824 | **0.4756** | 0.4840 | 0.0160 | Success |
| Pandoc (pdflatex) | 0.8377 | **0.8420** | 0.8412 | 0.0094 | Success |
| Pandoc (xelatex) | 1.5973 | **1.5374** | 1.5395 | 0.0146 | Success |

### Document: `large.md`

| Engine | Cold Start (s) | Warm Median (s) | Warm Mean (s) | Std Dev (s) | Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| Playwright (Chromium) | 0.4048 | **0.0482** | 0.0503 | 0.0055 | Success |
| md2pdf (native) | 0.2816 | **0.0497** | 0.0503 | 0.0016 | Success |
| Pandoc (weasyprint) | 0.5280 | **0.5321** | 0.5367 | 0.0169 | Success |
| Pandoc (pdflatex) | 0.8684 | **0.8424** | 0.8427 | 0.0130 | Success |
| Pandoc (xelatex) | 1.5188 | **1.5293** | 1.5351 | 0.0162 | Success |
