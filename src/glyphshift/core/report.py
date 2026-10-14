"""Batch conversion HTML reports (print-to-PDF friendly)."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

from glyphshift.core.models import ConversionResult


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def build_html_report(
    results: list[ConversionResult],
    *,
    title: str = "GlyphShift conversion report",
) -> str:
    """Return a self-contained HTML document summarizing ``results``."""
    converted = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rows: list[str] = []
    for r in results:
        status = "OK" if r.success else ("SKIP" if r.skipped else "FAIL")
        color = {"OK": "#0a7", "FAIL": "#c33", "SKIP": "#a80"}[status]
        verify = "-"
        if r.verify_report is not None:
            verify = "passed" if r.verify_report.passed else f"failed ({len(r.verify_report.errors)} err)"
        issues = ""
        if r.verify_report:
            bits = [f"[{i.severity.value}] {i.code}" for i in r.verify_report.issues[:8]]
            issues = "; ".join(bits)
        warn = "; ".join(r.warnings[:5])
        rows.append(
            "<tr>"
            f"<td style='color:{color};font-weight:600'>{_esc(status)}</td>"
            f"<td>{_esc(r.input_path)}</td>"
            f"<td>{_esc(r.output_path or '-')}</td>"
            f"<td>{_esc(r.input_format)}→{_esc(r.output_format)}</td>"
            f"<td>{'lossless' if r.lossless else 'lossy'}</td>"
            f"<td>{_esc(verify)}</td>"
            f"<td>{_esc(r.error or warn or issues or '-')}</td>"
            "</tr>"
        )

    table = "\n".join(rows) or "<tr><td colspan='7'>No results</td></tr>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{_esc(title)}</title>
<style>
  body {{ font-family: Segoe UI, Tahoma, sans-serif; margin: 2rem; color: #222; }}
  h1 {{ font-size: 1.4rem; }}
  .meta {{ color: #555; margin-bottom: 1rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.9rem; }}
  th, td {{ border: 1px solid #ddd; padding: 0.45rem 0.55rem; text-align: left; vertical-align: top; }}
  th {{ background: #f4f4f4; }}
  @media print {{ body {{ margin: 0.5rem; }} }}
</style>
</head>
<body>
  <h1>{_esc(title)}</h1>
  <p class="meta">Generated { _esc(now) } · {_esc(converted)} converted ·
     {_esc(failed)} failed · {_esc(skipped)} skipped · {_esc(len(results))} total</p>
  <p class="meta">Tip: use your browser Print → Save as PDF for an archival PDF copy.</p>
  <table>
    <thead>
      <tr>
        <th>Status</th><th>Input</th><th>Output</th><th>Format</th>
        <th>Mode</th><th>Verify</th><th>Notes</th>
      </tr>
    </thead>
    <tbody>
      {table}
    </tbody>
  </table>
</body>
</html>
"""


def write_html_report(
    results: list[ConversionResult],
    path: Path | str,
    *,
    title: str = "GlyphShift conversion report",
) -> Path:
    """Write HTML report to ``path`` and return the path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html_report(results, title=title), encoding="utf-8")
    return out
