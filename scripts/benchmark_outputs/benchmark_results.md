# Rendering Performance Report
**Date:** 2026-06-15 21:19:10
**Platform:** macOS-26.5.1-arm64-arm-64bit-Mach-O (arm)
**Python Version:** 3.13.5

## System Engine Versions
- **md2pdf (native)**: 0.5.3 (Available)
- **Pandoc (pdflatex)**: Pandoc 3.9.0.2 (pdflatex) (Available)
- **Pandoc (xelatex)**: Pandoc 3.9.0.2 (xelatex) (Available)
- **Pandoc (weasyprint)**: Pandoc 3.9.0.2 (weasyprint) (Available)
- **Playwright (Chromium)**: 1.60.0 (Available)

## Benchmark Summary

### Document: `simple.md`

| Engine | Cold Start (s) | Warm Median (s) | Warm Mean (s) | Std Dev (s) | Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| md2pdf (native) | 0.2362 | **0.0191** | 0.0231 | 0.0094 | Success |
| Playwright (Chromium) | 0.4758 | **0.0391** | 0.0411 | 0.0040 | Success |
| Pandoc (weasyprint) | 0.6235 | **0.3415** | 0.3408 | 0.0035 | Success |
| Pandoc (pdflatex) | 1.0007 | **0.7372** | 0.7413 | 0.0158 | Success |
| Pandoc (xelatex) | 1.5218 | **1.4280** | 1.4354 | 0.0267 | Success |

### Document: `medium.md`

| Engine | Cold Start (s) | Warm Median (s) | Warm Mean (s) | Std Dev (s) | Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| Playwright (Chromium) | 0.3878 | **0.0429** | 0.0441 | 0.0036 | Success |
| md2pdf (native) | 0.6990 | **0.0650** | 0.0882 | 0.0457 | Success |
| Pandoc (weasyprint) | 0.4712 | **0.4621** | 0.4634 | 0.0028 | Success |
| Pandoc (pdflatex) | 0.8464 | **0.8363** | 0.8537 | 0.0472 | Success |
| Pandoc (xelatex) | 1.5017 | **1.5009** | 1.5054 | 0.0219 | Success |

### Document: `large.md`

| Engine | Cold Start (s) | Warm Median (s) | Warm Mean (s) | Std Dev (s) | Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| Playwright (Chromium) | 0.3954 | **0.0471** | 0.0481 | 0.0041 | Success |
| md2pdf (native) | 0.2966 | **0.0701** | 0.0709 | 0.0016 | Success |
| Pandoc (weasyprint) | 0.5287 | **0.5179** | 0.5185 | 0.0087 | Success |
| Pandoc (pdflatex) | 0.8166 | **0.8305** | 0.8407 | 0.0227 | Success |
| Pandoc (xelatex) | 1.4976 | **1.5126** | 1.5196 | 0.0243 | Success |
