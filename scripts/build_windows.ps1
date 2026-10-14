# Build GlyphShift one-file Windows binaries (CLI + GUI).
# Run from repo root: powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> Installing package (dev + gui)…" -ForegroundColor Cyan
python -m pip install --upgrade pip
pip install -e ".[dev,gui]"

Write-Host "==> Building CLI (glyphshift.exe)…" -ForegroundColor Cyan
pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name glyphshift `
  --paths src `
  src\glyphshift\cli.py

Write-Host "==> Building GUI (glyphshift-gui.exe)…" -ForegroundColor Cyan
pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name glyphshift-gui `
  --paths src `
  --hidden-import PySide6 `
  --collect-all PySide6 `
  src\glyphshift\gui\__main__.py

$Out = Join-Path $Root "release-bin"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
Copy-Item (Join-Path $Root "dist\glyphshift.exe") (Join-Path $Out "glyphshift-windows.exe") -Force
Copy-Item (Join-Path $Root "dist\glyphshift-gui.exe") (Join-Path $Out "glyphshift-gui-windows.exe") -Force

Write-Host ""
Write-Host "Done. Binaries:" -ForegroundColor Green
Get-ChildItem $Out | ForEach-Object {
  "{0}`t{1:N1} MB" -f $_.Name, ($_.Length / 1MB)
}
Write-Host ""
Write-Host "Try: .\release-bin\glyphshift-windows.exe --version"
