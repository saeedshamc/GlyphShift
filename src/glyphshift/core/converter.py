"""Public conversion API used by CLI and GUI."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

from glyphshift.core.collection import extract_face, list_faces
from glyphshift.core.errors import (
    ConversionError,
    GlyphShiftError,
    OutputExistsError,
    VerificationError,
)
from glyphshift.core.formats import (
    Format,
    OutlineType,
    conversion_is_lossless,
    detect_format,
)
from glyphshift.core.models import ConversionOptions, ConversionResult, VerifyMode, VerifyReport
from glyphshift.core.outlines import cff_to_glyf, glyf_to_cff, instantiate_variable
from glyphshift.core.verify import verify
from glyphshift.core.wrapper import wrap_font

logger = logging.getLogger(__name__)

ProgressCb = Callable[[int, int, str], None]


def _compute_out_path(
    src: Path,
    dst: Path | None,
    target: Format,
    *,
    overwrite: bool,
    ttc_index: int | None,
) -> Path:
    if dst is not None and (dst.is_dir() or str(dst).endswith(("/", "\\"))):
        dst.mkdir(parents=True, exist_ok=True)
        stem = src.stem if ttc_index is None else f"{src.stem}-{ttc_index}"
        out = dst / f"{stem}{target.extension}"
    elif dst is None:
        stem = src.stem if ttc_index is None else f"{src.stem}-{ttc_index}"
        out = src.with_name(f"{stem}{target.extension}")
    else:
        out = dst

    if out.resolve() == src.resolve():
        raise ConversionError(f"Refusing to overwrite the input file in place: {src}")
    if out.exists() and not overwrite:
        raise OutputExistsError(f"Output already exists (use --overwrite): {out}")
    return out


def _safe_unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.exists():
            path.unlink()
    except OSError:
        logger.warning("Could not remove temporary file %s", path)


def convert_file(
    src: Path | str,
    dst: Path | None,
    target: Format | str,
    options: ConversionOptions | None = None,
) -> ConversionResult:
    """Convert a single font file to ``target`` format.

    Never modifies the input file. Writes via temp + atomic rename.
    """
    options = options or ConversionOptions()
    src = Path(src)
    dst_path = Path(dst) if dst is not None else None
    if isinstance(target, str):
        target = Format.from_string(target)

    t0 = time.perf_counter()
    warnings: list[str] = []
    size_before = src.stat().st_size if src.is_file() else 0
    input_format = "unknown"
    lossless = True
    temps: list[Path] = []
    verify_source: Path | None = None

    try:
        detected = detect_format(src, deep=True)
        input_format = detected.format.value
        warnings.extend(detected.warnings)
        lossless = conversion_is_lossless(detected.format, detected.outline, target)

        work_src = src
        ttc_index = options.ttc_index

        # --- Collections ---
        if detected.is_collection:
            faces = list_faces(src)
            idx = 0 if ttc_index is None else ttc_index
            if ttc_index is None and len(faces) > 1:
                warnings.append(
                    f"Collection has {len(faces)} faces; converting index 0. "
                    "Pass ttc_index / --index to select another face."
                )
            ttc_index = idx
            extract_dir = dst_path if dst_path and dst_path.is_dir() else src.parent
            extract_dir.mkdir(parents=True, exist_ok=True)
            extract_tmp = extract_dir / f".{src.stem}-{idx}.extract.tmp"
            work_src, extract_warns = extract_face(src, idx, extract_tmp, overwrite=True)
            warnings.extend(extract_warns)
            temps.append(work_src)
            verify_source = work_src
            detected = detect_format(work_src, deep=True)
            lossless = conversion_is_lossless(detected.format, detected.outline, target)
        else:
            verify_source = src

        # --- Optional instancing ---
        if options.instance and options.lossless_only:
            raise ConversionError(
                "Lossless-only mode refuses --instance (collapsing axes is lossy)."
            )
        if options.instance:
            inst_tmp = work_src.parent / f".{work_src.stem}.instance.tmp.ttf"
            work_src, inst_warns = instantiate_variable(
                work_src,
                inst_tmp,
                options.instance,
                overwrite=True,
                target=Format.TTF,
            )
            warnings.extend(inst_warns)
            temps.append(work_src)
            verify_source = work_src
            lossless = False
            detected = detect_format(work_src, deep=True)

        out_path = _compute_out_path(
            src,
            dst_path,
            target,
            overwrite=options.overwrite,
            ttc_index=ttc_index if src.suffix.lower() in {".ttc", ".otc"} else None,
        )

        # WOFF/WOFF2 keep source outlines; only TTF/OTF targets may force outline conversion.
        need_outline = False
        if target == Format.TTF:
            need_outline = detected.outline in (OutlineType.CFF, OutlineType.CFF2)
        elif target == Format.OTF:
            need_outline = detected.outline == OutlineType.GLYF

        if need_outline and options.lossless_only:
            raise ConversionError(
                "Lossless-only mode refuses outline conversion "
                f"({detected.outline.value} -> {target.value}). "
                "Use a wrapper target (woff/woff2) or disable lossless profile."
            )

        if need_outline and detected.is_variable and not options.instance:
            raise ConversionError(
                "Refusing outline conversion of a variable font without --instance. "
                "Wrapper conversions (e.g. variable TTF -> WOFF2) preserve variation tables."
            )

        # Pre-flight coverage advisories (Persian/Arabic).
        try:
            from glyphshift.core.coverage import coverage_warnings

            for iss in coverage_warnings(verify_source or src):
                if iss.severity.value in {"warning", "error"}:
                    warnings.append(f"[coverage:{iss.code}] {iss.message}")
        except Exception:  # noqa: BLE001
            logger.debug("Coverage scan skipped", exc_info=True)

        outline_converted = False
        outline_direction: str | None = None
        max_err_used = options.max_err
        final_path: Path

        if need_outline:
            lossless = False
            mid_dir = out_path.parent
            mid_dir.mkdir(parents=True, exist_ok=True)
            if detected.outline in (OutlineType.CFF, OutlineType.CFF2):
                mid = mid_dir / f".{out_path.stem}.cff2glyf.tmp.ttf"
                mid, ow, max_err_used = cff_to_glyf(
                    work_src,
                    mid,
                    max_err=options.max_err,
                    reverse_direction=options.reverse_direction,
                    overwrite=True,
                )
                warnings.extend(ow)
                temps.append(mid)
                outline_converted = True
                outline_direction = "cff_to_glyf"
                if target == Format.TTF:
                    if mid.resolve() != out_path.resolve():
                        if out_path.exists():
                            out_path.unlink()
                        mid.replace(out_path)
                        if mid in temps:
                            temps.remove(mid)
                    final_path = out_path
                else:
                    final_path = wrap_font(
                        mid,
                        out_path,
                        target,
                        overwrite=True,
                        preserve_flavor_data=options.preserve_flavor_data,
                    )
            else:
                mid = mid_dir / f".{out_path.stem}.glyf2cff.tmp.otf"
                mid, ow = glyf_to_cff(work_src, mid, overwrite=True)
                warnings.extend(ow)
                temps.append(mid)
                outline_converted = True
                outline_direction = "glyf_to_cff"
                if target == Format.OTF:
                    if mid.resolve() != out_path.resolve():
                        if out_path.exists():
                            out_path.unlink()
                        mid.replace(out_path)
                        if mid in temps:
                            temps.remove(mid)
                    final_path = out_path
                else:
                    final_path = wrap_font(
                        mid,
                        out_path,
                        target,
                        overwrite=True,
                        preserve_flavor_data=options.preserve_flavor_data,
                    )
        else:
            final_path = wrap_font(
                work_src,
                out_path,
                target,
                overwrite=options.overwrite,
                preserve_flavor_data=options.preserve_flavor_data,
            )

        verify_report: VerifyReport | None = None
        if options.verify and verify_source is not None:
            vmode = VerifyMode.TOLERANT if outline_converted else VerifyMode.STRICT
            verify_report = verify(
                verify_source,
                final_path,
                mode=vmode,
                max_err=max_err_used,
                outline_converted=outline_converted,
                direction=outline_direction,
            )
            if not verify_report.passed and vmode == VerifyMode.STRICT:
                if not options.keep_on_fail:
                    _safe_unlink(final_path)
                    final_path_out: Path | None = None
                else:
                    final_path_out = final_path
                # Clean temps before returning failure
                for p in temps:
                    if p.resolve() != (final_path_out.resolve() if final_path_out else None):
                        _safe_unlink(p)
                raise VerificationError(
                    f"Verification failed for {final_path}",
                    report=verify_report,
                )

        # Cleanup temps (not the final output)
        for p in temps:
            if p.resolve() != final_path.resolve():
                _safe_unlink(p)

        size_after = final_path.stat().st_size if final_path.exists() else None
        return ConversionResult(
            input_path=src,
            output_path=final_path,
            input_format=input_format,
            output_format=target.value,
            size_before=size_before,
            size_after=size_after,
            duration_seconds=time.perf_counter() - t0,
            verify_report=verify_report,
            warnings=warnings,
            success=True,
            lossless=lossless,
        )

    except VerificationError as exc:
        vr = exc.report if isinstance(exc.report, VerifyReport) else None
        return ConversionResult(
            input_path=src,
            output_path=None,
            input_format=input_format,
            output_format=target.value,
            size_before=size_before,
            size_after=None,
            duration_seconds=time.perf_counter() - t0,
            verify_report=vr,
            warnings=warnings,
            success=False,
            lossless=lossless,
            error=exc.message,
        )
    except GlyphShiftError as exc:
        for p in temps:
            _safe_unlink(p)
        return ConversionResult(
            input_path=src,
            output_path=None,
            input_format=input_format,
            output_format=target.value,
            size_before=size_before,
            size_after=None,
            duration_seconds=time.perf_counter() - t0,
            verify_report=None,
            warnings=warnings,
            success=False,
            lossless=lossless,
            error=exc.message,
        )
    except Exception as exc:
        logger.exception("Unexpected conversion error for %s", src)
        for p in temps:
            _safe_unlink(p)
        return ConversionResult(
            input_path=src,
            output_path=None,
            input_format=input_format,
            output_format=target.value,
            size_before=size_before,
            size_after=None,
            duration_seconds=time.perf_counter() - t0,
            verify_report=None,
            warnings=warnings,
            success=False,
            lossless=lossless,
            error=str(exc),
        )


def _clone_options(options: ConversionOptions, **updates: object) -> ConversionOptions:
    data = {
        "max_err": options.max_err,
        "reverse_direction": options.reverse_direction,
        "overwrite": options.overwrite,
        "verify": options.verify,
        "keep_on_fail": options.keep_on_fail,
        "ttc_index": options.ttc_index,
        "instance": options.instance,
        "recursive": options.recursive,
        "lossless_only": options.lossless_only,
        "preserve_flavor_data": options.preserve_flavor_data,
        "workers": options.workers,
        "record_history": options.record_history,
    }
    data.update(updates)
    return ConversionOptions(**data)  # type: ignore[arg-type]


def convert_many(
    sources: list[Path | str],
    out_dir: Path | str,
    target: Format | str,
    options: ConversionOptions | None = None,
    progress_cb: ProgressCb | None = None,
    cancel_event: object | None = None,
) -> list[ConversionResult]:
    """Convert many fonts into ``out_dir``.

    When ``options.workers`` > 1, jobs run in a thread pool (fontTools releases
    the GIL around much of I/O). ``cancel_event`` may be a ``threading.Event``.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    options = options or ConversionOptions()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(target, str):
        target = Format.from_string(target)

    paths = [Path(p) for p in sources]
    jobs: list[tuple[Path, ConversionOptions]] = []
    early: list[ConversionResult] = []

    for path in paths:
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            early.append(
                ConversionResult(
                    input_path=path,
                    output_path=None,
                    input_format="",
                    output_format=target.value,
                    size_before=0,
                    size_after=None,
                    duration_seconds=0.0,
                    verify_report=None,
                    warnings=["Cancelled"],
                    success=False,
                    skipped=True,
                    error="Cancelled",
                )
            )
            continue
        try:
            det = detect_format(path, deep=False)
        except GlyphShiftError as exc:
            early.append(
                ConversionResult(
                    input_path=path,
                    output_path=None,
                    input_format="unknown",
                    output_format=target.value,
                    size_before=0,
                    size_after=None,
                    duration_seconds=0.0,
                    verify_report=None,
                    success=False,
                    error=exc.message,
                )
            )
            continue

        if det.is_collection and options.ttc_index is None:
            try:
                faces = list_faces(path)
            except GlyphShiftError as exc:
                early.append(
                    ConversionResult(
                        input_path=path,
                        output_path=None,
                        input_format=det.format.value,
                        output_format=target.value,
                        size_before=path.stat().st_size,
                        size_after=None,
                        duration_seconds=0.0,
                        verify_report=None,
                        success=False,
                        error=exc.message,
                    )
                )
                continue
            for face in faces:
                jobs.append((path, _clone_options(options, ttc_index=face["index"])))
        else:
            jobs.append((path, options))

    results: list[ConversionResult] = list(early)
    total = len(jobs)
    workers = max(1, int(options.workers or 1))

    if workers == 1 or total <= 1:
        for i, (path, opts) in enumerate(jobs):
            if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                results.append(
                    ConversionResult(
                        input_path=path,
                        output_path=None,
                        input_format="",
                        output_format=target.value,
                        size_before=0,
                        size_after=None,
                        duration_seconds=0.0,
                        verify_report=None,
                        warnings=["Cancelled"],
                        success=False,
                        skipped=True,
                        error="Cancelled",
                    )
                )
                continue
            if progress_cb is not None:
                progress_cb(i, total, str(path))
            results.append(convert_file(path, out_dir, target, opts))
    else:
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(convert_file, path, out_dir, target, opts): path
                for path, opts in jobs
            }
            for fut in as_completed(futures):
                if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                    break
                results.append(fut.result())
                done += 1
                if progress_cb is not None:
                    progress_cb(done, total, str(futures[fut]))

    if progress_cb is not None:
        progress_cb(total, total, "")

    return results
