# Integrations & installers

## VS Code / Cursor

A minimal task runner lives in [`extras/vscode/`](../extras/vscode/).

Copy `.vscode/tasks.json` into your workspace (or open this repo) and run:

- **GlyphShift: Convert to WOFF2** — converts the active font file beside itself
- **GlyphShift: Font info** — prints metadata for the active file

Requires `glyphshift` on `PATH` (`pip install glyphshift` or `pip install -e .`).

A full marketplace extension (status bar, drag-drop panel) can wrap the same CLI; the task file is enough for daily use without publishing an extension.

## Figma

A native Figma plugin is **not** shipped yet. Recommended workflow today:

1. Export/download font files from Figma (or your design pipeline)
2. Convert with GlyphShift (`--profile web` → WOFF2)
3. Copy CSS via `glyphshift css FILE --bundle` or the GUI **Copy CSS** button
4. Paste `@font-face` into your site / design-token CSS

A future plugin could call a local GlyphShift daemon; tracking issue: open a GitHub issue titled `figma-plugin`.

## Standalone installers

GitHub Actions [`release.yml`](../.github/workflows/release.yml) builds **one-file** PyInstaller binaries per OS on tag `v*`:

| Artifact | Platform |
|----------|----------|
| `glyphshift-windows.exe` / `glyphshift-gui-windows.exe` | Windows |
| `glyphshift-macos` / `glyphshift-gui-macos` | macOS |
| `glyphshift-linux` / `glyphshift-gui-linux` | Linux |

PyInstaller cannot cross-compile — each OS builds its own binary.

Optional next step: wrap the Windows `.exe` in Inno Setup / MSI and the macOS binary in a `.dmg`. The Release assets are already installable by downloading and placing on `PATH`.

## Optional extras

```bash
pip install "glyphshift[gui]"     # desktop UI
pip install "glyphshift[shape]"   # HarfBuzz shaping checks
pip install "glyphshift[dev]"     # tests + ruff + pyinstaller
```
