"""Dataclasses for conversion options, results, and verification reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(str, Enum):
    """Issue severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class VerifyMode(str, Enum):
    """Verification strictness."""

    STRICT = "strict"
    TOLERANT = "tolerant"


@dataclass
class Issue:
    """A single verification or conversion issue."""

    severity: Severity
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class VerifyReport:
    """Result of comparing a source font against a converted output."""

    passed: bool
    mode: VerifyMode
    issues: list[Issue] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "mode": self.mode.value,
            "issues": [i.to_dict() for i in self.issues],
            "details": self.details,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }


@dataclass
class ConversionOptions:
    """Options controlling a single conversion or batch."""

    max_err: float = 1.0
    reverse_direction: bool = True
    overwrite: bool = False
    verify: bool = True
    keep_on_fail: bool = False
    ttc_index: int | None = None
    instance: str | None = None
    recursive: bool = False
    lossless_only: bool = False
    preserve_flavor_data: bool = True
    workers: int = 1
    record_history: bool = True


@dataclass
class ConversionResult:
    """Outcome of converting one source file (or one face from a collection)."""

    input_path: Path
    output_path: Path | None
    input_format: str
    output_format: str
    size_before: int
    size_after: int | None
    duration_seconds: float
    verify_report: VerifyReport | None
    warnings: list[str] = field(default_factory=list)
    success: bool = False
    lossless: bool = True
    error: str | None = None
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": str(self.input_path),
            "output_path": str(self.output_path) if self.output_path else None,
            "input_format": self.input_format,
            "output_format": self.output_format,
            "size_before": self.size_before,
            "size_after": self.size_after,
            "duration_seconds": self.duration_seconds,
            "verify_report": self.verify_report.to_dict() if self.verify_report else None,
            "warnings": list(self.warnings),
            "success": self.success,
            "lossless": self.lossless,
            "error": self.error,
            "skipped": self.skipped,
        }
