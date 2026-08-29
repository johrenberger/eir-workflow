"""Deterministic lineage checks across persisted EIR evidence artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _load(path: str | Path) -> tuple[Path, dict, str]:
    file = Path(path)
    raw = file.read_bytes()
    return file, json.loads(raw), hashlib.sha256(raw).hexdigest()


def verify_e1c_to_e2(baseline_path: str | Path, baseline_coverage_path: str | Path, e2_validation_path: str | Path, e2_coverage_path: str | Path) -> dict:
    baseline_file, baseline, baseline_hash = _load(baseline_path)
    baseline_coverage_file, baseline_coverage, baseline_coverage_hash = _load(baseline_coverage_path)
    e2_file, e2, e2_hash = _load(e2_validation_path)
    e2_coverage_file, e2_coverage, e2_coverage_hash = _load(e2_coverage_path)
    lineage = set(e2.get("evidence_lineage", []))
    required = {baseline_file.name, baseline_coverage_file.name}
    errors = []
    if not required <= lineage:
        errors.append("e2_missing_e1c_lineage_reference")
    if baseline.get("watchdog", {}).get("returncode") != 0:
        errors.append("e1c_baseline_not_successful")
    if e2.get("watchdog", {}).get("returncode") != 0:
        errors.append("e2_validation_not_successful")
    if not baseline_coverage.get("totals") or not e2_coverage.get("totals"):
        errors.append("coverage_totals_missing")
    return {
        "valid": not errors,
        "errors": errors,
        "artifacts": {
            "e1c_baseline": {"name": baseline_file.name, "sha256": baseline_hash},
            "e1c_coverage": {"name": baseline_coverage_file.name, "sha256": baseline_coverage_hash},
            "e2_validation": {"name": e2_file.name, "sha256": e2_hash},
            "e2_coverage": {"name": e2_coverage_file.name, "sha256": e2_coverage_hash},
        },
    }
