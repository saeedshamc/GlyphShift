"""Named conversion profiles (web / desktop / lossless-only)."""

from __future__ import annotations

from dataclasses import replace
from enum import Enum

from glyphshift.core.errors import GlyphShiftError
from glyphshift.core.formats import Format
from glyphshift.core.models import ConversionOptions


class Profile(str, Enum):
    """Built-in conversion presets."""

    WEB = "web"
    DESKTOP = "desktop"
    LOSSLESS = "lossless"

    @property
    def description(self) -> str:
        return {
            Profile.WEB: "WOFF2 for the web; verify on; never overwrite by default",
            Profile.DESKTOP: "Keep TTF/OTF for desktop apps; verify on",
            Profile.LOSSLESS: "Refuse any outline/instance conversion; container-only",
        }[self]


def profile_target(profile: Profile, source_format: Format | None = None) -> Format:
    """Default target format for a profile."""
    if profile == Profile.WEB:
        return Format.WOFF2
    if profile == Profile.DESKTOP:
        if source_format in (Format.OTF, Format.WOFF, Format.WOFF2):
            # Prefer matching outline family when known; default TTF.
            return Format.OTF if source_format == Format.OTF else Format.TTF
        return Format.TTF
    # lossless: keep container change to WOFF2 as the usual safe web path,
    # or same-family unwrap — callers often pass an explicit --to.
    return Format.WOFF2


def apply_profile(
    profile: Profile | str,
    options: ConversionOptions | None = None,
    *,
    target: Format | None = None,
) -> tuple[Format, ConversionOptions]:
    """Return (target_format, options) adjusted for ``profile``."""
    if isinstance(profile, str):
        try:
            profile = Profile(profile.lower())
        except ValueError as exc:
            raise GlyphShiftError(
                f"Unknown profile '{profile}'. Use: web, desktop, lossless"
            ) from exc

    opts = options or ConversionOptions()
    opts = replace(opts, verify=True)

    if profile == Profile.WEB:
        fmt = target or Format.WOFF2
        opts = replace(opts, verify=True)
    elif profile == Profile.DESKTOP:
        fmt = target or Format.TTF
        opts = replace(opts, verify=True)
    else:  # LOSSLESS
        fmt = target or Format.WOFF2
        opts = replace(opts, verify=True, instance=None)
        # Flag for converter: refuse outline conversion
        opts = replace(opts, lossless_only=True)

    return fmt, opts


def list_profiles() -> list[dict[str, str]]:
    return [
        {"id": p.value, "name": p.value, "description": p.description} for p in Profile
    ]
