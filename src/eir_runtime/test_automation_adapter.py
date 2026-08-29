"""Boundary-only semantics for deterministic Python test automation objectives."""
from __future__ import annotations

import re
import hashlib
import json
from .core import TerminalOutcome
from .validation import Diagnostic


class TestAutomationObjectiveAdapter:
    """Interprets a manifest and measurements; it never owns run lifecycle."""

    REQUIRED = {"objective_id", "target_module", "minimum_line_coverage", "allowed_change_paths", "production_paths"}

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
        if not all((after.get("valid_coverage"), after.get("production_unchanged"), after.get("full_suite_passed"), after.get("process_exit_code") == 0, after.get("watchdog_inactive"))):
            return {"improved": False, "reason": "invalid_measurement"}
        prior = float(before.get("target_line_coverage", 0.0)) if before else 0.0
        current = float(after.get("target_line_coverage", 0.0))
        return {"improved": current > prior, "reason": "line_coverage_increased" if current > prior else "no_measurable_improvement"}

    def measurement_from_evidence(self, manifest: dict, validation: dict, coverage: dict) -> dict:
        """Deterministically derive completion evidence from raw runner/tool output."""
        target = str(manifest["target_module"]).replace("/", "\\")
        files = coverage.get("files", {})
        target_report = next((report for path, report in files.items() if path.replace("/", "\\").endswith(target)), None)
        watchdog = validation.get("watchdog", {})
        stdout = str(validation.get("stdout", ""))
        passed = bool(re.search(r"\b\d+\s+passed\b", stdout))
        return {
            "target_line_coverage": target_report.get("summary", {}).get("percent_covered", 0.0) if target_report else 0.0,
            "minimum_line_coverage": manifest["minimum_line_coverage"],
            "full_suite_passed": passed and watchdog.get("returncode") == 0,
            "process_exit_code": watchdog.get("returncode"),
            "watchdog_inactive": watchdog.get("timed_out") is False,
            "production_unchanged": validation.get("production_unchanged") is True,
            "valid_coverage": bool(target_report and coverage.get("totals") and coverage.get("meta")),
            "evidence_artifact_hashes": {
                "validation": self._hash(validation),
                "coverage": self._hash(coverage),
            },
        }

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
        last = measurements[-1]["measurement"]
        return None if self._complete(last) else "next_test_candidate"

    def completion(self, state: dict, records: list[dict], *, exhausted: bool) -> tuple[TerminalOutcome, str]:
        measurements = [record["payload"]["measurement"] for record in records if record["record_type"] == "measurement"]
        if measurements and self._complete(measurements[-1]):
            return TerminalOutcome.SUPPORTED, "TEST_AUTOMATION_OBJECTIVE_COMPLETED"
        if exhausted:
            return TerminalOutcome.INSUFFICIENT_EVIDENCE, "TEST_AUTOMATION_ATTEMPTS_EXHAUSTED"
        return TerminalOutcome.FAILED, "PREMATURE_TERMINATION"

    def _complete(self, measurement: dict) -> bool:
        return all((
            measurement.get("target_line_coverage", 0.0) >= measurement.get("minimum_line_coverage", 101.0),
            measurement.get("full_suite_passed") is True,
            measurement.get("process_exit_code") == 0,
            measurement.get("watchdog_inactive") is True,
            measurement.get("production_unchanged") is True,
            measurement.get("valid_coverage") is True,
        ))

    @staticmethod
    def _hash(value: dict) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
