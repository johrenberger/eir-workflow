"""Deterministic Test Automation capability boundaries.

Raw pytest and coverage-tool schemas stop here; adapters consume normalized
records only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TestExecutionResult:
    __test__ = False
    collected: int
    passed: int
    failed: int
    errors: int
    skipped: int
    exit_code: int | None
    timed_out: bool
    duration_seconds: float
    collection_errors: int = 0

    @property
    def full_suite_passed(self) -> bool:
        return bool(self.collected >= 0 and self.collected == self.passed + self.skipped and self.passed >= 0 and self.failed == 0 and self.errors == 0 and self.collection_errors == 0 and self.exit_code == 0 and not self.timed_out)

    @classmethod
    def from_structured(cls, payload: dict[str, Any]) -> "TestExecutionResult":
        required = {"collected", "passed", "failed", "errors", "skipped", "exit_code", "timed_out", "duration_seconds"}
        missing = required - set(payload)
        if missing:
            raise ValueError(f"structured execution result missing: {', '.join(sorted(missing))}")
        return cls(**{key: payload[key] for key in required}, collection_errors=payload.get("collection_errors", 0))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FileCoverage:
    path: str
    line_coverage: float
    branch_coverage: float | None
    missing_lines: tuple[int, ...]
    missing_branches: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class CoverageResult:
    total_line_coverage: float
    total_branch_coverage: float | None
    files: tuple[FileCoverage, ...]
    valid: bool
    target: FileCoverage | None


class CoverageCapability:
    def normalize(self, raw: dict[str, Any], target_module: str) -> CoverageResult:
        files = []
        target = None
        normalized_target = target_module.replace("/", "\\")
        for path, report in raw.get("files", {}).items():
            summary = report.get("summary", {})
            branches = summary.get("percent_branches_covered")
            record = FileCoverage(
                path=path,
                line_coverage=float(summary.get("percent_covered", 0.0)),
                branch_coverage=float(branches) if branches is not None else None,
                missing_lines=tuple(report.get("missing_lines", [])),
                missing_branches=tuple(tuple(item) for item in report.get("missing_branches", [])),
            )
            files.append(record)
            if path.replace("/", "\\").endswith(normalized_target):
                target = record
        totals = raw.get("totals", {})
        branch_total = totals.get("percent_branches_covered")
        valid = bool(raw.get("meta") and totals and target)
        return CoverageResult(
            total_line_coverage=float(totals.get("percent_covered", 0.0)),
            total_branch_coverage=float(branch_total) if branch_total is not None else None,
            files=tuple(files), valid=valid, target=target,
        )
