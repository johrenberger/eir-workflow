"""Field-mapped comparison between original E2 and shared-controller replay audits."""
from __future__ import annotations

import json
from pathlib import Path


def compare_e2_audits(original_path: str | Path, migrated_path: str | Path) -> dict:
    original = json.loads(Path(original_path).read_text(encoding="utf-8"))
    migrated = json.loads(Path(migrated_path).read_text(encoding="utf-8"))
    original_validation = original["validation"]
    checks = [
        ("terminal_outcome", original["terminal_outcome"], migrated["outcome"]),
        ("target_line_coverage", original_validation["user_module"]["summary"]["percent_covered"], migrated["measurement"]["target_line_coverage"]),
        ("process_exit_code", original_validation["watchdog"]["returncode"], migrated["measurement"]["process_exit_code"]),
        ("watchdog_inactive", not original_validation["watchdog"]["timed_out"], migrated["measurement"]["watchdog_inactive"]),
        ("production_unchanged", original_validation["production_unchanged"], migrated["measurement"]["production_unchanged"]),
        ("test_only_change_set_valid", True, migrated["change_set"]["valid"]),
        ("lineage_valid", True, migrated["lineage"]["valid"]),
    ]
    fields = [{"field": name, "original": expected, "migrated": actual, "equal": expected == actual} for name, expected, actual in checks]
    return {"valid": all(field["equal"] for field in fields), "fields": fields}
