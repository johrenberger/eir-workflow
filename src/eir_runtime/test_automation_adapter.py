"""Boundary-only semantics for deterministic Python test automation objectives."""
from __future__ import annotations

import hashlib
import json
from .core import TerminalOutcome
from .test_capabilities import CoverageCapability, TestExecutionResult
from .test_quality import MutationResult, QualityEvaluator, derive_gaps, select_gap
from .validation import Diagnostic


class TestAutomationObjectiveAdapter:
    """Interprets a manifest and measurements; it never owns run lifecycle."""

    __test__ = False

    REQUIRED = {"objective_id", "target_module", "minimum_line_coverage", "allowed_change_paths", "production_paths"}

    def __init__(self, *, coverage: CoverageCapability | None = None, quality: QualityEvaluator | None = None):
        self.coverage = coverage or CoverageCapability()
        self.quality = quality or QualityEvaluator()

    def validate_contract(self, manifest: dict) -> list[Diagnostic]:
        missing = sorted(self.REQUIRED - set(manifest))
        if missing:
            return [Diagnostic("TA001", "objective", f"missing required fields: {', '.join(missing)}")]
        if not isinstance(manifest["minimum_line_coverage"], (int, float)) or not 0 <= manifest["minimum_line_coverage"] <= 100:
            return [Diagnostic("TA002", "objective.minimum_line_coverage", "must be a percentage from 0 to 100")]
        if not manifest["allowed_change_paths"] or not manifest["production_paths"]:
            return [Diagnostic("TA003", "objective", "allowed and production path sets are required")]
        return []

    def compare(self, before: dict | None, after: dict) -> dict:
        return self.quality.progress(before, after, after["objective_manifest"])

    def measurement_from_evidence(self, manifest: dict, validation: dict, coverage: dict, mutation: MutationResult | None = None) -> dict:
        """Deterministically derive completion evidence from raw runner/tool output."""
        execution = TestExecutionResult.from_structured(validation.get("test_execution", {}))
        normalized_coverage = self.coverage.normalize(coverage, manifest["target_module"])
        target = normalized_coverage.target
        watchdog = validation.get("watchdog", {})
        measurement = {
            "objective_manifest": manifest,
            "target_module": manifest["target_module"],
            "test_execution": execution.as_dict(),
            "target_line_coverage": target.line_coverage if target else 0.0,
            "target_branch_coverage": target.branch_coverage if target else None,
            "missing_lines": list(target.missing_lines) if target else [],
            "missing_branches": [list(branch) for branch in target.missing_branches] if target else [],
            "total_line_coverage": normalized_coverage.total_line_coverage,
            "total_branch_coverage": normalized_coverage.total_branch_coverage,
            "minimum_line_coverage": manifest["minimum_line_coverage"],
            "minimum_branch_coverage": manifest.get("minimum_branch_coverage"),
            "full_suite_passed": execution.full_suite_passed,
            "process_exit_code": execution.exit_code,
            "watchdog_inactive": not execution.timed_out and watchdog.get("timed_out") is False,
            "production_unchanged": validation.get("production_unchanged") is True,
            "valid_coverage": normalized_coverage.valid,
            "evidence_artifact_hashes": {
                "validation": self._hash(validation),
                "coverage": self._hash(coverage),
            },
        }
        if mutation:
            measurement.update({"mutation_score": mutation.mutation_score, "surviving_mutants": mutation.survived, "mutation_valid": not mutation.invalid, "surviving_mutant_details": list(mutation.surviving_mutants)})
        gaps = derive_gaps(measurement, mutation)
        measurement["gaps"] = gaps
        measurement["unresolved_behavior_gaps"] = len(gaps)
        return measurement

    def validate_change_set(self, manifest: dict, changed_paths: list[str]) -> dict:
        """Allow only manifest-approved test paths; reject production or unknown paths."""
        normalize = lambda value: str(value).replace("\\", "/").lstrip("./")
        allowed = {normalize(value) for value in manifest["allowed_change_paths"]}
        production = {normalize(value) for value in manifest["production_paths"]}
        changed = {normalize(value) for value in changed_paths}
        rejected = sorted(changed - allowed)
        production_changed = sorted(changed & production)
        return {"valid": not rejected and not production_changed, "changed": sorted(changed), "rejected": rejected, "production_changed": production_changed}

    def recovery_unit(self, state: dict, records: list[dict]) -> str | None:
        measurements = [record["payload"] for record in records if record["record_type"] == "measurement"]
        if not measurements:
            return "baseline_measurement"
        if any(record["record_type"] == "repository_mismatch" for record in records):
            return "reconcile_repository"
        last = measurements[-1]["measurement"]
        return None if self._complete(last) else ("next_test_gap" if self.select_gap(last) else "next_test_candidate")

    def completion(self, state: dict, records: list[dict], *, exhausted: bool) -> tuple[TerminalOutcome, str]:
        measurements = [record["payload"]["measurement"] for record in records if record["record_type"] == "measurement"]
        if measurements and self._complete(measurements[-1]):
            return TerminalOutcome.SUPPORTED, "TEST_AUTOMATION_OBJECTIVE_COMPLETED"
        if exhausted:
            return TerminalOutcome.INSUFFICIENT_EVIDENCE, "TEST_AUTOMATION_ATTEMPTS_EXHAUSTED"
        return TerminalOutcome.FAILED, "PREMATURE_TERMINATION"

    def _complete(self, measurement: dict) -> bool:
        return self.quality.complete(measurement, measurement["objective_manifest"])

    def derive_gaps(self, measurement: dict) -> list[dict]:
        return measurement["gaps"] if "gaps" in measurement else derive_gaps(measurement)

    def select_gap(self, measurement: dict) -> dict | None:
        return select_gap(self.derive_gaps(measurement))

    def reconcile_gaps(self, records: list[dict], measurement: dict) -> list[dict]:
        """Reconcile adapter-owned TestGap records without changing EIR state."""
        prior_records = [record["payload"] for record in records if record["record_type"] == "test_gaps"]
        prior = {gap["id"]: gap for gap in (prior_records[-1]["gaps"] if prior_records else [])}
        current = {gap["id"]: gap for gap in self.derive_gaps(measurement)}
        reconciled = []
        for gap_id in sorted(set(prior) | set(current)):
            old, observed = prior.get(gap_id), current.get(gap_id)
            if observed is None:
                reconciled.append({**old, "status": "resolved"})
            elif old and old.get("status") == "unresolved":
                reconciled.append({**observed, "attempts": old.get("attempts", 0)})
            else:
                reconciled.append(observed)
        return reconciled

    def select_persisted_gap(self, records: list[dict]) -> dict | None:
        gap_records = [record["payload"] for record in records if record["record_type"] == "test_gaps"]
        return select_gap(gap_records[-1]["gaps"]) if gap_records else None

    @staticmethod
    def _hash(value: dict) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
