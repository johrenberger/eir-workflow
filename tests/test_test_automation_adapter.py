import json
from pathlib import Path

from eir_runtime import ActionKey, RunController, RunStore, TerminalOutcome
from eir_runtime.test_automation_adapter import TestAutomationObjectiveAdapter


FIXTURE = Path(__file__).parents[1] / "fixtures" / "test-automation-e2.json"
INVALID_FIXTURE = Path(__file__).parents[1] / "fixtures" / "test-automation-e2-invalid-coverage.json"
TIMEOUT_FIXTURE = Path(__file__).parents[1] / "fixtures" / "test-automation-e2-timeout.json"


def measurement(coverage, **overrides):
    value = {"target_line_coverage": coverage, "minimum_line_coverage": 90.0, "full_suite_passed": True, "process_exit_code": 0, "watchdog_inactive": True, "production_unchanged": True, "valid_coverage": True}
    value.update(overrides)
    return value


def test_test_adapter_uses_generic_controller_for_progress_and_completion(tmp_path):
    manifest = json.loads(FIXTURE.read_text())
    store = RunStore(tmp_path / "state.sqlite")
    controller = RunController(store, TestAutomationObjectiveAdapter())
    controller.start("e2", manifest)
    key = ActionKey("TEST_CANDIDATE", "app/user.py", "L1", "candidate-01")
    assert controller.record_measurement("e2", key, measurement(86.9))["improved"]
    assert controller.recover("e2") == "next_test_candidate"
    key2 = ActionKey("TEST_CANDIDATE", "app/user.py", "L2", "candidate-02")
    assert controller.record_measurement("e2", key2, measurement(90.48))["improved"]
    assert controller.complete("e2", exhausted=False) == TerminalOutcome.SUPPORTED
    assert store.load("e2")["terminal"] == "SUPPORTED"
    store.close()


def test_test_adapter_rejects_invalid_measurement_and_preserves_noncompletion(tmp_path):
    manifest = json.loads(FIXTURE.read_text())
    store = RunStore(tmp_path / "state.sqlite")
    controller = RunController(store, TestAutomationObjectiveAdapter())
    controller.start("e2", manifest)
    decision = controller.record_measurement("e2", ActionKey("TEST_CANDIDATE", "app/user.py", "L1", "candidate"), measurement(95.0, production_unchanged=False))
    assert decision == {"improved": False, "reason": "invalid_measurement"}
    assert controller.complete("e2", exhausted=True) == TerminalOutcome.INSUFFICIENT_EVIDENCE
    store.close()


def test_e2_negative_fixture_missing_target_coverage_cannot_advance_progress(tmp_path):
    manifest = json.loads(FIXTURE.read_text())
    raw = json.loads(INVALID_FIXTURE.read_text())
    store = RunStore(tmp_path / "state.sqlite")
    controller = RunController(store, TestAutomationObjectiveAdapter())
    controller.start("e2", manifest)
    derived = controller.adapter.measurement_from_evidence(manifest, raw["validation"], raw["coverage"])
    assert derived["valid_coverage"] is False and derived["target_line_coverage"] == 0.0
    decision = controller.record_measurement("e2", ActionKey("TEST_CANDIDATE", "app/user.py", "L1", "missing-target"), derived)
    assert decision == {"improved": False, "reason": "invalid_measurement"}
    assert store.conn.execute("SELECT status FROM actions WHERE action_id='TEST_CANDIDATE'").fetchone()[0] == "NO_PROGRESS"
    store.close()


def test_e2_evidence_ingestion_derives_valid_completion_measurement():
    manifest = json.loads(FIXTURE.read_text())
    validation = {"watchdog": {"returncode": 0, "timed_out": False}, "stdout": "16 passed in 1.19s", "production_unchanged": True}
    coverage = {"meta": {"version": "7.16.0"}, "totals": {"percent_covered": 95.21}, "files": {r"F:\coding\pytest-fastapi-crud-example\app\user.py": {"summary": {"percent_covered": 90.48}}}}
    derived = TestAutomationObjectiveAdapter().measurement_from_evidence(manifest, validation, coverage)
    assert derived["valid_coverage"] and derived["full_suite_passed"] and derived["target_line_coverage"] == 90.48
    assert set(derived["evidence_artifact_hashes"]) == {"validation", "coverage"}


def test_test_adapter_enforces_manifest_test_only_allowlist():
    manifest = json.loads(FIXTURE.read_text())
    adapter = TestAutomationObjectiveAdapter()
    assert adapter.validate_change_set(manifest, ["tests/test_crud_api.py", "tests\\test_user_exceptions.py"])["valid"]
    rejected = adapter.validate_change_set(manifest, ["tests/test_crud_api.py", "app/user.py", "README.md"])
    assert not rejected["valid"] and rejected["production_changed"] == ["app/user.py"] and rejected["rejected"] == ["README.md", "app/user.py"]


def test_timeout_fixture_is_invalid_progress_and_routes_to_generic_h1(tmp_path):
    manifest = json.loads(FIXTURE.read_text())
    raw = json.loads(TIMEOUT_FIXTURE.read_text())
    store = RunStore(tmp_path / "state.sqlite")
    controller = RunController(store, TestAutomationObjectiveAdapter())
    controller.start("e2", manifest)
    key = ActionKey("TEST_CANDIDATE", "app/user.py", "L4", "timeout-evidence")
    measurement = controller.adapter.measurement_from_evidence(manifest, raw["validation"], raw["coverage"])
    assert controller.record_measurement("e2", key, measurement) == {"improved": False, "reason": "invalid_measurement"}
    for _ in range(2):
        controller.lifecycle.record_failure("e2", key, signature="POSTPASS_TIMEOUT", phase="RESEARCHING")
    assert controller.control_route("e2", key, signature="POSTPASS_TIMEOUT", max_attempts_per_strategy=2, max_total_attempts=8, max_l4_attempts=2, requires_human=True) == "H1"
    assert controller.handoff("e2", key, reason="watchdog remained active after pass output", evidence=measurement)["strategy_id"] == "L5"
    store.close()
