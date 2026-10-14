# GlyphShift

[![CI](https://github.com/SaeedShamsi/GlyphShift/actions/workflows/ci.yml/badge.svg)](https://github.com/SaeedShamsi/GlyphShift/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/badge/PyPI-glyphshift-blue.svg)](https://pypi.org/project/glyphshift/)

**GlyphShift** is a lossless, cross-platform font converter for **TTF**, **OTF**, **WOFF** and **WOFF2**. It ships as a CLI (`glyphshift`) and a desktop GUI (`glyphshift-gui`) that share one core library. Every conversion is automatically verified so glyphs, OpenType features, and metadata — especially Persian/Arabic shaping data — are not silently lost.

## Features

- **Lossless container conversions** between TTF/OTF and WOFF/WOFF2 (no subsetting, no table drops)
- **Optional outline conversion** (CFF ↔ TrueType) with explicit lossy warnings
- **Profiles**: `web` → WOFF2, `desktop`, `lossless` (refuses outline/instance paths)
- **Automatic verification** after every convert (cmap, glyph order, GSUB/GPOS, metrics, names)
- **HarfBuzz shaping checks** (`glyphshift shape`, optional `pip install "glyphshift[shape]"`)
- **Persian/Arabic coverage** advisories (ZWNJ, digits, GSUB/GPOS) before convert
- **HTML batch reports** (print-to-PDF) and **parallel workers**
- **CSS `@font-face`** helper with `unicode-range` presets
- **Watch folder**, **conversion history** with safe undo (deletes outputs only)
- **TTC/OTC** collection listing and splitting
- **Variable fonts**: wrapper keeps `fvar`/`gvar`/`avar`/…; optional axis instancing
- CLI + GUI on Windows, macOS, and Linux

## Conversion matrix

| From → To | TTF | OTF | WOFF | WOFF2 |
|-----------|-----|-----|------|-------|
| **TTF (glyf)** | — | LOSSY¹ | LOSSLESS | LOSSLESS |
| **OTF (CFF)** | LOSSY² | — | LOSSLESS | LOSSLESS |
| **WOFF** | LOSSLESS* | LOSSLESS* | LOSSLESS | LOSSLESS |
| **WOFF2** | LOSSLESS* | LOSSLESS* | LOSSLESS | LOSSLESS |

\*Lossless when the target matches the source outline type; otherwise an outline conversion is required.

1. **TTF → OTF:** geometry is exact (quadratic→cubic); TrueType hinting (`fpgm`/`prep`/`cvt`/glyph programs) is dropped.
2. **OTF → TTF:** cubics are approximated with quadratics (`max_err`); CFF hinting is dropped; TrueType hinting is not generated (use `ttfautohint` externally if needed).

Glyph count, glyph names/order, full cmap, GSUB/GPOS/GDEF, and name/legal records are preserved and verified in both paths.

> Verification compares **decompiled table content**, not raw bytes. WOFF2 applies a reversible transform to `glyf`/`loca`/`hmtx`, so round-trips are table-content-equivalent, not byte-identical.

## Installation

```bash
pip install glyphshift
pip install "glyphshift[gui]"     # PySide6 desktop UI
pip install "glyphshift[shape]"   # HarfBuzz shaping checks
pipx install glyphshift           # isolated CLI
```

Standalone one-file binaries are attached to [GitHub Releases](https://github.com/SaeedShamsi/GlyphShift/releases) (built on each OS with PyInstaller — PyInstaller cannot cross-compile).

- How to build locally on **Windows / macOS / Linux**: [docs/BUILD.md](docs/BUILD.md)
- VS Code tasks, Figma workflow, installer notes: [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)

```powershell
# Windows (this machine)
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
# → release-bin\glyphshift-windows.exe
# → release-bin\glyphshift-gui-windows.exe
```

## CLI usage

```bash
glyphshift convert font.ttf --profile web
glyphshift convert fonts/ --to woff2 --out out/ -r --workers 4 --report out/report.html
glyphshift convert arabic.otf --to ttf --max-err 1.0   # lossy outline path
glyphshift info font.ttf --json
glyphshift coverage font.ttf
glyphshift shape source.ttf converted.woff2
glyphshift css font.woff2 --bundle
glyphshift watch ./drop --to woff2 --out ./out
glyphshift history --limit 20
glyphshift verify source.ttf converted.woff2 --strict
glyphshift profiles
glyphshift formats
```

Exit codes: `0` success · `1` some failures · `2` usage error · `3` verification failure.

## GUI usage

```bash
pip install "glyphshift[gui]"
glyphshift-gui
# or: python -m glyphshift.gui
```

- Drag-and-drop files/folders, **profiles**, target format, advanced options (workers, WOFF metadata)
- Live **LOSSLESS / LOSSY** indicator; optional variable-axis instancing
- Background conversion with progress and cancel; light/dark theme
- Side-by-side preview (Latin / Persian / digits / ZWNJ / Arabic), RTL-aware
- Verification report, coverage panel, history undo, CSS unicode-range copy, English ⇄ فارسی

<!-- Screenshots: add docs/screenshots/*.png when available -->

## Verification (“never loses glyphs”)

After every conversion GlyphShift runs `verify(src, dst)`:

1. Glyph count and exact glyph order/names  
2. All cmap subtables (plus critical Arabic/Persian code points)  
3. Table presence (accounting for intentional outline-conversion removals)  
4. Metrics (`hmtx`/`vmtx`/`head`/`hhea`/`OS/2`)  
5. Layout tables via semantic XML (`GSUB`/`GPOS`/`GDEF`/…) and script/feature tags  
6. Full `name` table  
7. Outlines: identical in wrapper mode; tolerance check in outline mode  
8. Variation tables preserved when present  

Strict mode (wrappers): any difference is an error and the output is deleted (unless `--keep-on-fail`). Tolerant mode (outline conversion): expected differences become warnings.

## Persian / Arabic notes

Fonts with Arabic shaping rely on GSUB/GPOS glyph **names/IDs**. GlyphShift never renames or reorders glyphs. Wrapper conversions are the recommended path for web deployment (`TTF/OTF → WOFF2`). Always keep the verification report green before shipping.

## Architecture

```
CLI / GUI  ──►  glyphshift.core  ──►  fontTools (+ brotli for WOFF2)
                 formats, wrapper, outlines, collection,
                 verify, info, converter
```

The CLI and GUI contain **zero** conversion logic; they only call `glyphshift.core`.

## Development

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -e ".[dev,gui]"
python tests/fixtures/build_fixtures.py
pytest
ruff check src tests
ruff format src tests
```

CI runs on Ubuntu, Windows, and macOS × Python 3.9–3.12 (ruff + pytest, `QT_QPA_PLATFORM=offscreen` for GUI).

### Assumptions

- “TTF” means TrueType outlines (`glyf`); “OTF” means CFF/CFF2 outlines (`OTTO`). A `.otf` file that is actually glyf-based is detected by tables, not by extension.
- Extension mismatches produce warnings, not hard errors.
- Default output policy: never overwrite; refuse and report (use `--overwrite`).
- Variable-font outline conversion requires `--instance` (intentionally lossy).

## Contributing

Issues and PRs welcome. Please run `ruff` and `pytest` before submitting. Do not add `fontTools.subset` or any code path that drops glyphs/tables during wrapper conversion.

## License & credits

MIT — see [LICENSE](LICENSE).

Core engine: [fontTools](https://github.com/fonttools/fonttools) (+ Brotli for WOFF2). Synthetic test fixtures are generated for CI; optional real OFL fonts (e.g. Vazirmatn) are documented under `tests/fixtures/`.
