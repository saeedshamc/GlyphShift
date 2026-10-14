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
    required=False,
    default=None,
    type=click.Choice(["ttf", "otf", "woff", "woff2"], case_sensitive=False),
    help="Target format (optional when --profile is set).",
)
@click.option(
    "--profile",
    type=click.Choice(["web", "desktop", "lossless"], case_sensitive=False),
    default=None,
    help="Preset: web→woff2, desktop→ttf/otf, lossless refuses outline conversion.",
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
@click.option("--workers", type=int, default=1, show_default=True, help="Parallel workers.")
@click.option("--report", "report_path", type=click.Path(path_type=Path), default=None)
@click.option("--no-flavor-data", is_flag=True, help="Drop WOFF metadata/private data.")
@click.option("--no-history", is_flag=True, help="Do not record conversion history.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output.")
@click.pass_context
def convert_cmd(
    ctx: click.Context,
    inputs: tuple[Path, ...],
    target: str | None,
    profile: str | None,
    out_dir: Path | None,
    overwrite: bool,
    max_err: float,
    no_verify: bool,
    keep_on_fail: bool,
    ttc_index: int | None,
    instance: str | None,
    recursive: bool,
    workers: int,
    report_path: Path | None,
    no_flavor_data: bool,
    no_history: bool,
    as_json: bool,
) -> None:
    """Convert font INPUT(s) to the given format."""
    from glyphshift.core.converter import convert_many
    from glyphshift.core.profiles import apply_profile
    from glyphshift.core.report import write_html_report

    try:
        files = _collect_inputs(inputs, recursive=recursive)
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if not files:
        raise click.ClickException("No font files found.")

    opts = ConversionOptions(
        max_err=max_err,
        overwrite=overwrite,
        verify=not no_verify,
        keep_on_fail=keep_on_fail,
        ttc_index=ttc_index,
        instance=instance,
        recursive=recursive,
        workers=max(1, workers),
        preserve_flavor_data=not no_flavor_data,
        record_history=not no_history,
    )

    if profile:
        explicit = Format.from_string(target) if target else None
        fmt, opts = apply_profile(profile, opts, target=explicit)
    elif target:
        fmt = Format.from_string(target)
    else:
        raise click.ClickException("Provide --to FORMAT or --profile NAME")

    dest = out_dir if out_dir is not None else (files[0].parent if len(files) > 1 else None)
    if dest is None:
        # Single file, write beside source via convert_file path logic
        results = []
        verify_failures = 0
        if not as_json:
            click.echo(f"Converting {len(files)} file(s) to {fmt.value.upper()}…")
        for path in files:
            _lossless, label = _lossless_label(path, fmt)
            if not as_json and not ctx.obj.get("quiet"):
                click.echo(f"{path}: {label}", err=True)
            result = convert_file(path, None, fmt, opts)
            results.append(result)
            if not result.success and result.verify_report and not result.verify_report.passed:
                verify_failures += 1
            if not as_json:
                _print_result(result, as_json=False)
    else:
        Path(dest).mkdir(parents=True, exist_ok=True)
        if not as_json:
            click.echo(
                f"Converting {len(files)} file(s) to {fmt.value.upper()} (workers={opts.workers})…"
            )

        def progress(done: int, total: int, current: str) -> None:
            if as_json or ctx.obj.get("quiet"):
                return
            if current:
                click.echo(f"[{done}/{total}] {current}", err=True)

        results = convert_many(files, dest, fmt, opts, progress_cb=progress)
        verify_failures = sum(
            1 for r in results if not r.success and r.verify_report and not r.verify_report.passed
        )
        if not as_json:
            for result in results:
                _print_result(result, as_json=False)

    if report_path is not None:
        write_html_report(results, report_path)

    converted = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)

    payload: dict[str, Any] = {
        "converted": converted,
        "failed": failed,
        "skipped": skipped,
        "results": [r.to_dict() for r in results],
    }
    if report_path is not None:
        payload["report"] = str(report_path)

    if as_json:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        click.echo()
        click.echo(
            f"Summary: {click.style(str(converted), fg='green')} converted, "
            f"{click.style(str(skipped), fg='yellow')} skipped, "
            f"{click.style(str(failed), fg='red')} failed"
        )
        if report_path is not None:
            click.echo(f"Report: {report_path}")

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
    click.echo()
    click.echo("Profiles: web, desktop, lossless  (see: glyphshift profiles)")


@main.command("profiles")
@click.option("--json", "as_json", is_flag=True)
def profiles_cmd(as_json: bool) -> None:
    """List built-in conversion profiles."""
    from glyphshift.core.profiles import list_profiles

    data = list_profiles()
    if as_json:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return
    for p in data:
        click.echo(f"{p['id']}: {p['description']}")


@main.command("css")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--preset", default=None, help="latin|arabic|persian (or omit for bundle)")
@click.option("--url", default=None, help="Override url(...) path in CSS")
@click.option("--bundle", is_flag=True, help="Emit suggested presets as multiple rules")
def css_cmd(file: Path, preset: str | None, url: str | None, bundle: bool) -> None:
    """Generate @font-face CSS (with unicode-range)."""
    from glyphshift.core.css import font_face_bundle, font_face_css

    if bundle or preset is None:
        click.echo(font_face_bundle(file, url=url))
    else:
        click.echo(font_face_css(file, url=url, unicode_range_preset=preset))


@main.command("coverage")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True)
def coverage_cmd(file: Path, as_json: bool) -> None:
    """Persian/Arabic coverage advisories before conversion."""
    from glyphshift.core.coverage import coverage_warnings, format_coverage_summary

    issues = coverage_warnings(file)
    if as_json:
        click.echo(json.dumps([i.to_dict() for i in issues], ensure_ascii=False, indent=2))
        return
    click.echo(format_coverage_summary(file))


@main.command("shape")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument(
    "other", required=False, type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def shape_cmd(ctx: click.Context, file: Path, other: Path | None, as_json: bool) -> None:
    """HarfBuzz shaping check (optional: compare FILE vs OTHER)."""
    from glyphshift.core.shaping import compare_shaping, shape_samples

    report = compare_shaping(file, other) if other else shape_samples(file)
    if as_json:
        click.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        status = (
            click.style("PASSED", fg="green")
            if report.passed
            else click.style("FAILED/WARN", fg="yellow")
        )
        click.echo(f"Shaping {status} (harfbuzz={'yes' if report.available else 'no'})")
        for sample in report.samples:
            click.echo(f"  {sample.name}: {len(sample.glyph_names)} glyphs")
        for iss in report.issues:
            color = {"error": "red", "warning": "yellow", "info": "cyan"}[iss.severity.value]
            click.echo(click.style(f"  [{iss.severity.value}] {iss.code}: {iss.message}", fg=color))
    if report.available and not report.passed:
        ctx.exit(EXIT_VERIFY)
    ctx.exit(EXIT_OK)


@main.command("history")
@click.option("--limit", default=20, show_default=True)
@click.option("--undo", "undo_id", default=None, help="Undo entry id (deletes output only).")
@click.option("--json", "as_json", is_flag=True)
def history_cmd(limit: int, undo_id: str | None, as_json: bool) -> None:
    """Show or undo recent conversions."""
    from glyphshift.core.history import list_history, undo_entry

    if undo_id:
        entry = undo_entry(undo_id, delete_output=True)
        click.echo(
            json.dumps(entry.to_dict(), ensure_ascii=False, indent=2)
            if as_json
            else f"Undone {entry.id}"
        )
        return
    entries = list_history(limit=limit)
    if as_json:
        click.echo(json.dumps([e.to_dict() for e in entries], ensure_ascii=False, indent=2))
        return
    if not entries:
        click.echo("No history.")
        return
    for e in entries:
        flag = "OK" if e.success else "FAIL"
        click.echo(f"{e.id[:8]}  {flag}  {e.input_path} -> {e.output_path or '-'}")


@main.command("watch")
@click.argument("folder", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--to", "target", required=True, type=click.Choice(["ttf", "otf", "woff", "woff2"]))
@click.option("--out", "out_dir", required=True, type=click.Path(path_type=Path))
@click.option("--interval", default=2.0, show_default=True)
@click.option("--overwrite", is_flag=True)
@click.option("--profile", type=click.Choice(["web", "desktop", "lossless"]), default=None)
def watch_cmd(
    folder: Path,
    target: str,
    out_dir: Path,
    interval: float,
    overwrite: bool,
    profile: str | None,
) -> None:
    """Watch FOLDER and convert new/changed fonts (Ctrl+C to stop)."""
    from glyphshift.core.profiles import apply_profile
    from glyphshift.core.watch import watch_folder

    opts = ConversionOptions(overwrite=overwrite, verify=True)
    fmt = Format.from_string(target)
    if profile:
        fmt, opts = apply_profile(profile, opts, target=fmt)
    click.echo(f"Watching {folder} → {out_dir} ({fmt.value}). Ctrl+C to stop.")
    try:
        watch_folder(
            folder,
            out_dir,
            fmt,
            opts,
            interval=interval,
            on_result=lambda r: _print_result(r, as_json=False),
        )
    except KeyboardInterrupt:
        click.echo("\nStopped.")


if __name__ == "__main__":
    main()
