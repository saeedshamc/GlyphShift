"""Pre-conversion coverage warnings for Persian/Arabic fonts."""

from __future__ import annotations

from pathlib import Path

from glyphshift.core.info import inspect_font
from glyphshift.core.models import Issue, Severity

CRITICAL_FEATURES = ("init", "medi", "fina", "isol", "rlig", "mark", "mkmk")


def coverage_warnings(path: Path | str) -> list[Issue]:
    """Return advisory issues about missing Arabic/Persian essentials."""
    info = inspect_font(path)
    issues: list[Issue] = []

    looks_arabic = info.has_arabic or "arab" in info.scripts
    if not looks_arabic:
        return issues

    if not info.has_zwnj:
        issues.append(
            Issue(
                Severity.WARNING,
                "missing_zwnj",
                "Font looks Arabic/Persian but U+200C (ZWNJ) is not mapped",
            )
        )
    if not info.has_persian_digits:
        issues.append(
            Issue(
                Severity.WARNING,
                "missing_persian_digits",
                "Persian digits U+06F0–U+06F9 are not mapped",
            )
        )
    if not info.has_arabic_indic_digits:
        issues.append(
            Issue(
                Severity.INFO,
                "missing_arabic_indic_digits",
                "Arabic-Indic digits U+0660–U+0669 are not mapped",
            )
        )
    if not info.has_gsub:
        issues.append(
            Issue(
                Severity.WARNING,
                "missing_gsub",
                "No GSUB table — Arabic shaping features may be absent",
            )
        )
    if not info.has_gpos:
        issues.append(
            Issue(
                Severity.WARNING,
                "missing_gpos",
                "No GPOS table — mark positioning / kerning may be absent",
            )
        )
    if "arab" not in info.scripts and info.has_gsub:
        issues.append(
            Issue(
                Severity.WARNING,
                "missing_arab_script",
                "GSUB present but 'arab' script tag not listed",
            )
        )

    return issues


def format_coverage_summary(path: Path | str) -> str:
    info = inspect_font(path)
    issues = coverage_warnings(path)
    lines = [
        f"{Path(path).name}: {info.mapped_codepoints} codepoints, "
        f"scripts={','.join(info.scripts) or '-'}, "
        f"zwnj={info.has_zwnj}, persian_digits={info.has_persian_digits}",
    ]
    for iss in issues:
        lines.append(f"  [{iss.severity.value}] {iss.code}: {iss.message}")
    if not issues and (info.has_arabic or "arab" in info.scripts):
        lines.append("  coverage looks complete for common Persian/Arabic checks")
    return "\n".join(lines)
