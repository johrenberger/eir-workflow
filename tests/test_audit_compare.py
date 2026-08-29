import json

from eir_runtime.audit_compare import compare_e2_audits


def test_e2_audit_comparator_maps_original_and_migrated_terminal_predicates(tmp_path):
    original = tmp_path / "original.json"; migrated = tmp_path / "migrated.json"
    original.write_text(json.dumps({"terminal_outcome": "SUPPORTED", "validation": {"user_module": {"summary": {"percent_covered": 90.48}}, "watchdog": {"returncode": 0, "timed_out": False}, "production_unchanged": True}}))
    migrated.write_text(json.dumps({"outcome": "SUPPORTED", "measurement": {"target_line_coverage": 90.48, "process_exit_code": 0, "watchdog_inactive": True, "production_unchanged": True}, "change_set": {"valid": True}, "lineage": {"valid": True}}))
    assert compare_e2_audits(original, migrated)["valid"]
