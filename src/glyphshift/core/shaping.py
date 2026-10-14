"""HarfBuzz-based shaping checks for Persian/Arabic sample texts."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from glyphshift.core.models import Issue, Severity

logger = logging.getLogger(__name__)

# Representative samples that exercise joining, ZWNJ, digits, and marks.
DEFAULT_SAMPLES: tuple[tuple[str, str], ...] = (
    ("persian_pangram", "ژاله از چرت‌های فارسی لذت می‌برد"),
    ("zwnj", "می‌روم کتاب‌ها دانش‌آموز"),
    ("persian_digits", "سال ۱۴۰۳"),
    ("arabic_marks", "بِسْمِ اللَّهِ"),
    ("lam_alef", "لا السلام علیکم"),
)


@dataclass
class ShapeSampleResult:
    name: str
    text: str
    glyph_names: list[str]
    cluster_count: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "text": self.text,
            "glyph_names": list(self.glyph_names),
            "cluster_count": self.cluster_count,
            "error": self.error,
        }


@dataclass
class ShapeReport:
    available: bool
    samples: list[ShapeSampleResult] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.available and not any(i.severity == Severity.ERROR for i in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "passed": self.passed,
            "samples": [s.to_dict() for s in self.samples],
            "issues": [i.to_dict() for i in self.issues],
            "details": self.details,
        }


def harfbuzz_available() -> bool:
    try:
        import uharfbuzz  # noqa: F401

        return True
    except ImportError:
        return False


def _sfnt_bytes(font_path: Path) -> bytes:
    """Return raw sfnt bytes (unwrap WOFF/WOFF2 so HarfBuzz sees full tables)."""
    magic = font_path.read_bytes()[:4]
    if magic in (b"wOFF", b"wOF2"):
        import io

        from fontTools.ttLib import TTFont

        font = TTFont(str(font_path), recalcTimestamp=False, recalcBBoxes=False)
        try:
            font.flavor = None
            buf = io.BytesIO()
            font.save(buf)
            return buf.getvalue()
        finally:
            font.close()
    return font_path.read_bytes()


def _shape_text(font_path: Path, text: str) -> ShapeSampleResult:
    import uharfbuzz as hb

    data = _sfnt_bytes(font_path)
    face = hb.Face(data)
    font = hb.Font(face)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    features = {"kern": True, "liga": True, "rlig": True, "calt": True, "mark": True, "mkmk": True}
    hb.shape(font, buf, features)
    infos = buf.glyph_infos
    names: list[str] = []
    for info in infos:
        gid = info.codepoint
        try:
            names.append(font.get_glyph_name(gid) or f"gid{gid}")
        except Exception:
            names.append(f"gid{gid}")
    return ShapeSampleResult(
        name="",
        text=text,
        glyph_names=names,
        cluster_count=len(infos),
    )


def shape_samples(
    font_path: Path | str,
    samples: tuple[tuple[str, str], ...] | None = None,
) -> ShapeReport:
    """Shape default (or custom) samples with HarfBuzz."""
    path = Path(font_path)
    if not harfbuzz_available():
        return ShapeReport(
            available=False,
            issues=[
                Issue(
                    Severity.WARNING,
                    "harfbuzz_missing",
                    "uharfbuzz is not installed; shaping checks skipped "
                    "(pip install 'glyphshift[shape]')",
                )
            ],
        )

    use = samples or DEFAULT_SAMPLES
    report = ShapeReport(available=True)
    for name, text in use:
        try:
            sample = _shape_text(path, text)
            sample.name = name
            report.samples.append(sample)
            if sample.cluster_count == 0 and text.strip():
                report.issues.append(
                    Issue(
                        Severity.ERROR,
                        f"empty_shape_{name}",
                        f"Shaping produced no glyphs for sample '{name}'",
                    )
                )
        except Exception as exc:
            logger.warning("Shaping failed for %s (%s): %s", path, name, exc)
            report.samples.append(
                ShapeSampleResult(
                    name=name, text=text, glyph_names=[], cluster_count=0, error=str(exc)
                )
            )
            report.issues.append(
                Issue(Severity.ERROR, f"shape_error_{name}", f"Shaping '{name}' failed: {exc}")
            )
    return report


def compare_shaping(
    src: Path | str,
    dst: Path | str,
    samples: tuple[tuple[str, str], ...] | None = None,
) -> ShapeReport:
    """Compare HarfBuzz glyph sequences between source and converted fonts."""
    if not harfbuzz_available():
        return shape_samples(src, samples)

    src_report = shape_samples(src, samples)
    dst_report = shape_samples(dst, samples)
    issues = list(src_report.issues) + list(dst_report.issues)

    src_map = {s.name: s for s in src_report.samples}
    dst_map = {s.name: s for s in dst_report.samples}
    for name in src_map:
        if name not in dst_map:
            issues.append(
                Issue(
                    Severity.ERROR, f"missing_sample_{name}", f"Sample '{name}' missing in output"
                )
            )
            continue
        a, b = src_map[name], dst_map[name]
        if a.error or b.error:
            continue
        if a.glyph_names != b.glyph_names:
            issues.append(
                Issue(
                    Severity.ERROR,
                    f"shape_mismatch_{name}",
                    f"Shaping glyph sequence differs for '{name}': "
                    f"{a.glyph_names} -> {b.glyph_names}",
                )
            )

    return ShapeReport(
        available=True,
        samples=dst_report.samples,
        issues=issues,
        details={"compared_to": str(src)},
    )
