#!/usr/bin/env bash
# Build GlyphShift one-file binaries on macOS or Linux.
# Usage (from repo root):
#   ./scripts/build_unix.sh macos
#   ./scripts/build_unix.sh linux

set -euo pipefail

OS_LABEL="${1:-}"
if [[ "$OS_LABEL" != "macos" && "$OS_LABEL" != "linux" ]]; then
  echo "Usage: $0 macos|linux" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Installing package (dev + gui)…"
python3 -m pip install --upgrade pip
pip install -e ".[dev,gui]"

echo "==> Building CLI…"
pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name glyphshift \
  --paths src \
  src/glyphshift/cli.py

echo "==> Building GUI…"
pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --windowed \
  --name glyphshift-gui \
  --paths src \
  --hidden-import PySide6 \
  --collect-all PySide6 \
  src/glyphshift/gui/__main__.py

mkdir -p release-bin
cp -f dist/glyphshift "release-bin/glyphshift-${OS_LABEL}"
cp -f dist/glyphshift-gui "release-bin/glyphshift-gui-${OS_LABEL}"
chmod +x "release-bin/glyphshift-${OS_LABEL}" "release-bin/glyphshift-gui-${OS_LABEL}"

echo ""
echo "Done. Binaries:"
ls -lh release-bin/glyphshift*"${OS_LABEL}"*
echo ""
echo "Try: ./release-bin/glyphshift-${OS_LABEL} --version"
