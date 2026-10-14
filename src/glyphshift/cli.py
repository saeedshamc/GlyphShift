"""GlyphShift command-line interface."""

from __future__ import annotations

import contextlib
import json
import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import click

from glyphshift import __version__
from glyphshift.core.converter import convert_file
from glyphshift.core.errors import GlyphShiftError
from glyphshift.core.formats import Format, conversion_is_lossless, detect_format
from glyphshift.core.info import inspect_font
from glyphshift.core.models import ConversionOptions, ConversionResult, VerifyMode
from glyphshift.core.verify import verify

EXIT_OK = 0
EXIT_SOME_FAILURES = 1
EXIT_USAGE = 2
EXIT_VERIFY = 3

FONT_GLOBS = ("*.ttf", "*.otf", "*.woff", "*.woff2", "*.ttc", "*.otc")


def _configure_stdio() -> None:
    """Best-effort UTF-8 stdout/stderr on Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


def _setup_logging(verbose: int, quiet: bool) -> None:
    if quiet:
        level = logging.ERROR
    elif verbose >= 2:
        level = logging.DEBUG
    elif verbose == 1:
        level = logging.INFO
    else:
        level = logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _collect_inputs(inputs: Iterable[Path], *, recursive: bool) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        if item.is_file():
            files.append(item)
        elif item.is_dir():
            pattern_iter = item.rglob if recursive else item.glob
            for pattern in FONT_GLOBS:
                files.extend(sorted(pattern_iter(pattern)))
        else:
            raise click.ClickException(f"Not found: {item}")
    # Deduplicate while preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for f in files:
        rp = f.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(f)
    return unique


def _lossless_label(src: Path, target: Format) -> tuple[bool, str]:
    try:
        det = detect_format(src, deep=True)
    except GlyphShiftError:
        return True, "UNKNOWN"
    lossless = conversion_is_lossless(det.format, det.outline, target)
    if target == Format.TTF and det.outline.value in {"cff", "cff2"}:
        lossless = False
    if target == Format.OTF and det.outline.value == "glyf":
        lossless = False
    if lossless:
        return True, "LOSSLESS"
    return False, "LOSSY (outline approximation / hinting dropped)"


def _print_result(result: ConversionResult, *, as_json: bool) -> None:
    if as_json:
        return
    status = click.style("OK", fg="green") if result.success else click.style("FAIL", fg="red")
    kind = "LOSSLESS" if result.lossless else "LOSSY"
    kind_s = click.style(kind, fg="green" if result.lossless else "yellow")
    out = result.output_path or "-"
    click.echo(f"  [{status}] [{kind_s}] {result.input_path} -> {out}")
    if result.error:
        click.echo(click.style(f"         error: {result.error}", fg="red"))
    for w in result.warnings:
        click.echo(click.style(f"         warning: {w}", fg="yellow"))
    if result.verify_report is not None:
        vr = result.verify_report
        if vr.passed:
            click.echo(click.style("         verify: passed", fg="green"))
        else:
            click.echo(
                click.style(
                    f"         verify: FAILED ({len(vr.errors)} errors, {len(vr.warnings)} warnings)",
                    fg="red",
                )
            )
            for iss in vr.errors[:5]:
                click.echo(f"           - [{iss.code}] {iss.message}")


@click.group()
@click.version_option(__version__, prog_name="glyphshift")
@click.option("-v", "--verbose", count=True, help="Increase log verbosity.")
@click.option("-q", "--quiet", is_flag=True, help="Only show errors.")
@click.pass_context
def main(ctx: click.Context, verbose: int, quiet: bool) -> None:
    """GlyphShift — lossless font converter (TTF/OTF/WOFF/WOFF2)."""
    _configure_stdio()
    _setup_logging(verbose, quiet)
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet


@main.command("convert")
@click.argument("inputs", nargs=-1, required=True, type=click.Path(path_type=Path))
@click.option(
    "--to",
    "target",
    required=True,
    type=click.Choice(["ttf", "otf", "woff", "woff2"], case_sensitive=False),
    help="Target format.",
)
@click.option(
    "--out", "out_dir", type=click.Path(path_type=Path), default=None, help="Output directory."
)
@click.option("--overwrite", is_flag=True, help="Overwrite existing outputs.")
@click.option(
    "--max-err",
    type=float,
    default=1.0,
    show_default=True,
    help="CFF->TTF approximation tolerance.",
)
@click.option("--no-verify", is_flag=True, help="Skip post-conversion verification.")
@click.option("--keep-on-fail", is_flag=True, help="Keep output even if verification fails.")
@click.option("--index", "ttc_index", type=int, default=None, help="TTC/OTC face index.")
@click.option("--instance", default=None, help="Variable instance, e.g. wght=400.")
@click.option("--recursive", "-r", is_flag=True, help="Recurse into directories.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output.")
@click.pass_context
def convert_cmd(
    ctx: click.Context,
    inputs: tuple[Path, ...],
    target: str,
    out_dir: Path | None,
    overwrite: bool,
    max_err: float,
    no_verify: bool,
    keep_on_fail: bool,
    ttc_index: int | None,
    instance: str | None,
    recursive: bool,
    as_json: bool,
) -> None:
    """Convert font INPUT(s) to the given format."""
    try:
        files = _collect_inputs(inputs, recursive=recursive)
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if not files:
        raise click.ClickException("No font files found.")

    fmt = Format.from_string(target)
    opts = ConversionOptions(
        max_err=max_err,
        overwrite=overwrite,
        verify=not no_verify,
        keep_on_fail=keep_on_fail,
        ttc_index=ttc_index,
        instance=instance,
        recursive=recursive,
    )

    results: list[ConversionResult] = []
    verify_failures = 0

    if not as_json:
        click.echo(f"Converting {len(files)} file(s) to {fmt.value.upper()}…")

    def _run_one(path: Path) -> ConversionResult:
        _lossless, label = _lossless_label(path, fmt)
        if not as_json and not ctx.obj.get("quiet"):
            click.echo(f"{path}: {label}", err=True)
        dest = out_dir if out_dir is not None else (path.parent if len(files) > 1 else None)
        return convert_file(path, dest, fmt, opts)

    if as_json or ctx.obj.get("quiet"):
        iterable: Iterable[Path] = files
        for path in iterable:
            result = _run_one(path)
            results.append(result)
            if not result.success and result.verify_report and not result.verify_report.passed:
                verify_failures += 1
    else:
        with click.progressbar(files, label="convert", show_pos=True, file=sys.stderr) as bar:
            for path in bar:
                result = _run_one(path)
                results.append(result)
                if not result.success and result.verify_report and not result.verify_report.passed:
                    verify_failures += 1
                _print_result(result, as_json=False)

    converted = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)

    payload: dict[str, Any] = {
        "converted": converted,
        "failed": failed,
        "skipped": skipped,
        "results": [r.to_dict() for r in results],
    }

    if as_json:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        click.echo()
        click.echo(
            f"Summary: {click.style(str(converted), fg='green')} converted, "
            f"{click.style(str(skipped), fg='yellow')} skipped, "
            f"{click.style(str(failed), fg='red')} failed"
        )

    if verify_failures and failed:
        ctx.exit(EXIT_VERIFY)
    if failed:
        ctx.exit(EXIT_SOME_FAILURES)
    ctx.exit(EXIT_OK)


@main.command("info")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True)
def info_cmd(file: Path, as_json: bool) -> None:
    """Show metadata for a font FILE."""
    try:
        info = inspect_font(file)
    except GlyphShiftError as exc:
        raise click.ClickException(exc.message) from exc
    if as_json:
        click.echo(json.dumps(info.to_dict(), ensure_ascii=False, indent=2))
        return
    click.echo(f"File:        {info.path}")
    click.echo(f"Format:      {info.format} (outline={info.outline}, flavor={info.flavor})")
    click.echo(f"Family:      {info.family}")
    click.echo(f"Subfamily:   {info.subfamily}")
    click.echo(f"Full name:   {info.full_name}")
    click.echo(f"PostScript:  {info.postscript_name}")
    click.echo(f"Version:     {info.version}")
    click.echo(f"Designer:    {info.designer}")
    click.echo(f"License:     {info.license}")
    click.echo(f"Glyphs:      {info.glyph_count}")
    click.echo(f"Units/em:    {info.units_per_em}")
    click.echo(f"Codepoints:  {info.mapped_codepoints}")
    click.echo(f"Scripts:     {', '.join(info.scripts) or '-'}")
    click.echo(f"Variable:    {info.is_variable} {info.axes or ''}")
    flags = []
    if info.has_arabic:
        flags.append("arabic")
    if info.has_persian_digits:
        flags.append("persian-digits")
    if info.has_arabic_indic_digits:
        flags.append("arabic-indic-digits")
    if info.has_zwnj:
        flags.append("zwnj")
    if info.has_gsub:
        flags.append("GSUB")
    if info.has_gpos:
        flags.append("GPOS")
    click.echo(f"Flags:       {', '.join(flags) or '-'}")


@main.command("verify")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("converted", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--strict/--tolerant", default=True, help="Verification mode.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def verify_cmd(
    ctx: click.Context,
    source: Path,
    converted: Path,
    strict: bool,
    as_json: bool,
) -> None:
    """Verify that CONVERTED is equivalent to SOURCE."""
    mode = VerifyMode.STRICT if strict else VerifyMode.TOLERANT
    report = verify(source, converted, mode)
    if as_json:
        click.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        status = (
            click.style("PASSED", fg="green") if report.passed else click.style("FAILED", fg="red")
        )
        click.echo(f"Verification {status} ({mode.value})")
        for iss in report.issues:
            color = {"error": "red", "warning": "yellow", "info": "cyan"}[iss.severity.value]
            click.echo(click.style(f"  [{iss.severity.value}] {iss.code}: {iss.message}", fg=color))
    if not report.passed:
        ctx.exit(EXIT_VERIFY)
    ctx.exit(EXIT_OK)


@main.command("formats")
def formats_cmd() -> None:
    """List supported conversions and which are lossless."""
    click.echo("Supported formats: ttf, otf, woff, woff2 (plus ttc/otc as input)")
    click.echo()
    click.echo("LOSSLESS (container only):")
    click.echo("  TTF/OTF <-> WOFF <-> WOFF2  (same outline technology)")
    click.echo()
    click.echo("LOSSY (outline conversion):")
    click.echo("  OTF (CFF) -> TTF (glyf): curve approximation; CFF hints dropped")
    click.echo("  TTF (glyf) -> OTF (CFF): geometry exact; TrueType hints dropped")
    click.echo()
    click.echo("Variable fonts: wrapper conversions keep fvar/gvar/avar/…;")
    click.echo("  outline conversion refused unless --instance is used (lossy).")


if __name__ == "__main__":
    main()
