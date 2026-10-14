# GlyphShift

[![CI](https://github.com/SaeedShamsi/GlyphShift/actions/workflows/ci.yml/badge.svg)](https://github.com/SaeedShamsi/GlyphShift/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)

**GlyphShift** is a lossless, cross-platform font converter (CLI + GUI) for TTF, OTF, WOFF and WOFF2. Every conversion is automatically verified so glyphs, OpenType features and metadata — especially Persian/Arabic shaping data — are not silently lost.

> Full documentation is expanded as the project matures. See below for installation and usage.

## Features

- Lossless container conversions between TTF/OTF and WOFF/WOFF2
- Optional CFF ↔ TrueType outline conversion with clear lossy warnings
- Automatic post-conversion verification (cmap, GSUB/GPOS, metrics, glyph order)
- Persian/Arabic aware checks (ZWNJ, Persian digits, `arab` features)
- CLI (`glyphshift`) and desktop GUI (`glyphshift-gui`) sharing one core library
- TTC/OTC collection splitting
- Variable-font wrapper support; outline conversion refused unless `--instance` is used

## Conversion matrix

| From → To | TTF | OTF | WOFF | WOFF2 |
|-----------|-----|-----|------|-------|
| **TTF (glyf)** | — | LOSSY (hints dropped) | LOSSLESS | LOSSLESS |
| **OTF (CFF)** | LOSSY (approx + hints dropped) | — | LOSSLESS | LOSSLESS |
| **WOFF** | LOSSLESS* | LOSSLESS* | LOSSLESS | LOSSLESS |
| **WOFF2** | LOSSLESS* | LOSSLESS* | LOSSLESS | LOSSLESS |

\*Lossless when the target matches the source outline type; otherwise an outline conversion is required.

**What “lossy” means:** curve approximation (CFF→TTF), dropped CFF or TrueType hinting, and (if `--instance` is used) collapsed variation axes. Glyphs, names, cmap, GSUB/GPOS and legal metadata are still preserved and verified.

## Installation

```bash
pip install glyphshift
# or with GUI:
pip install "glyphshift[gui]"
# or isolated:
pipx install glyphshift
```

Standalone binaries are attached to GitHub Releases (built per-OS with PyInstaller; PyInstaller cannot cross-compile).

## CLI

```bash
glyphshift convert font.ttf --to woff2
glyphshift convert fonts/ --to woff --out out/ --recursive
glyphshift info font.ttf
glyphshift verify source.ttf converted.woff2 --strict
glyphshift formats
```

## GUI

```bash
pip install "glyphshift[gui]"
glyphshift-gui
# or: python -m glyphshift.gui
```

## Development

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -e ".[dev,gui]"
pytest
ruff check src tests
```

## License

MIT — see [LICENSE](LICENSE). Built on [fontTools](https://github.com/fonttools/fonttools).
