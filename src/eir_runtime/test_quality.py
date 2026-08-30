"""Deterministic multi-dimensional quality semantics for Test Automation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MutationResult:
    total_mutants: int
    killed: int
    survived: int
    timed_out: int
    invalid: bool
    surviving_mutants: tuple[dict[str, Any], ...] = ()

    @property
    def mutation_score(self) -> float | None:
        if self.invalid or self.total_mutants <= 0:
            return None
        return self.killed / self.total_mutants * 100.0


@dataclass(frozen=True)
class QualityState:
    tests_passing: bool
    line_coverage: float
    branch_coverage: float | None
    mutation_score: float | None
    surviving_mutants: int | None
    unresolved_behavior_gaps: int
    regressions: int
    policy_violations: int


class QualityEvaluator:
    """Configured quality gates and monotonic progress; no model input."""

    def state(self, measurement: dict) -> QualityState:
        return QualityState(
            tests_passing=bool(measurement.get("full_suite_passed")),
            line_coverage=float(measurement.get("target_line_coverage", 0.0)),
            branch_coverage=measurement.get("target_branch_coverage"),
            mutation_score=measurement.get("mutation_score"),
            surviving_mutants=measurement.get("surviving_mutants"),
            unresolved_behavior_gaps=int(measurement.get("unresolved_behavior_gaps", 0)),
            regressions=int(measurement.get("regressions", 0)),
            policy_violations=int(measurement.get("policy_violations", 0)),
        )

    def progress(self, before: dict | None, after: dict, manifest: dict) -> dict:
        current = self.state(after)
        if not self._evidence_valid(after, manifest):
            return {"improved": False, "reason": "invalid_measurement"}
        previous = self.state(before or {})
        configured = self._configured(manifest)
        regressions = self._regressions(previous, current, configured, manifest)
        if regressions:
            return {"improved": False, "reason": "required_metric_regression", "regressions": regressions}
        improved = []
        if "line" in configured and current.line_coverage > previous.line_coverage: improved.append("line_coverage")
        if "branch" in configured and current.branch_coverage is not None and (previous.branch_coverage is None or current.branch_coverage > previous.branch_coverage): improved.append("branch_coverage")
        if "mutation" in configured and current.mutation_score is not None and (previous.mutation_score is None or current.mutation_score > previous.mutation_score): improved.append("mutation_score")
        if "mutation" in configured and current.surviving_mutants is not None and (previous.surviving_mutants is None or current.surviving_mutants < previous.surviving_mutants): improved.append("surviving_mutants")
        if current.unresolved_behavior_gaps < previous.unresolved_behavior_gaps: improved.append("unresolved_behavior_gaps")
        return {"improved": bool(improved), "reason": improved[0] if improved else "no_measurable_improvement", "dimensions": improved}

    def complete(self, measurement: dict, manifest: dict) -> bool:
        state = self.state(measurement)
        if not self._evidence_valid(measurement, manifest):
            return False
        if state.line_coverage < manifest["minimum_line_coverage"]: return False
        if manifest.get("minimum_branch_coverage") is not None and (state.branch_coverage is None or state.branch_coverage < manifest["minimum_branch_coverage"]): return False
        if manifest.get("minimum_mutation_score") is not None and (state.mutation_score is None or state.mutation_score < manifest["minimum_mutation_score"]): return False
        if manifest.get("maximum_unresolved_behavior_gaps") is not None and state.unresolved_behavior_gaps > manifest["maximum_unresolved_behavior_gaps"]: return False
        return True

    @staticmethod
    def valid(measurement: dict) -> bool:
        return bool(measurement.get("valid_coverage") and measurement.get("production_unchanged") and measurement.get("full_suite_passed") and measurement.get("process_exit_code") == 0 and measurement.get("watchdog_inactive") and not measurement.get("policy_violations", 0) and not measurement.get("regressions", 0))

    def _evidence_valid(self, measurement: dict, manifest: dict) -> bool:
        if not self.valid(measurement):
            return False
        if manifest.get("minimum_branch_coverage") is not None and measurement.get("target_branch_coverage") is None:
            return False
        if manifest.get("minimum_mutation_score") is not None and measurement.get("mutation_score") is None:
            return False
        return True

    @staticmethod
    def _configured(manifest: dict) -> set[str]:
        return {"line"} | ({"branch"} if manifest.get("minimum_branch_coverage") is not None else set()) | ({"mutation"} if manifest.get("minimum_mutation_score") is not None else set())

    @staticmethod
    def _regressions(before: QualityState, after: QualityState, configured: set[str], manifest: dict) -> list[str]:
        tolerance = manifest.get("regression_tolerances", {})
        result = []
        for name, old, new in (("line", before.line_coverage, after.line_coverage), ("branch", before.branch_coverage, after.branch_coverage), ("mutation", before.mutation_score, after.mutation_score)):
            if name in configured and old is not None and new is not None and new < old - float(tolerance.get(name, 0.0)):
                result.append(name)
        return result


def derive_gaps(measurement: dict, mutation: MutationResult | None = None) -> list[dict]:
    target = measurement.get("target_module", "target")
    gaps = [{"id": f"line:{target}:{line}", "target": target, "type": "uncovered_line", "evidence": {"line": line}, "priority": 10, "status": "unresolved", "attempts": 0} for line in measurement.get("missing_lines", [])]
    gaps += [{"id": f"branch:{target}:{left}->{right}", "target": target, "type": "uncovered_branch", "evidence": {"branch": [left, right]}, "priority": 100, "status": "unresolved", "attempts": 0} for left, right in measurement.get("missing_branches", [])]
    if mutation and not mutation.invalid:
        gaps += [{"id": f"mutant:{item['id']}", "target": item.get("target", target), "type": "surviving_mutant", "evidence": item, "priority": 80, "status": "unresolved", "attempts": 0} for item in mutation.surviving_mutants]
    return gaps


def select_gap(gaps: list[dict]) -> dict | None:
    candidates = [gap for gap in gaps if gap.get("status") == "unresolved"]
    return min(candidates, key=lambda gap: (-int(gap.get("priority", 0)), int(gap.get("attempts", 0)), gap["id"])) if candidates else None
