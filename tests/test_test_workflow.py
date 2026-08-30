from eir_runtime import ActionKey, RunController, RunStore
from eir_runtime.test_automation_adapter import TestAutomationObjectiveAdapter
from eir_runtime.test_workflow import TestAutomationWorkflow


def manifest():
    return {"objective_id": "ta", "target_module": "app/user.py", "minimum_line_coverage": 90, "allowed_change_paths": ["tests/test_user.py"], "production_paths": ["app/user.py"]}


def measurement(lines, branches):
    return {"objective_manifest": manifest(), "target_module": "app/user.py", "target_line_coverage": 80, "target_branch_coverage": 70, "missing_lines": lines, "missing_branches": branches, "full_suite_passed": True, "process_exit_code": 0, "watchdog_inactive": True, "production_unchanged": True, "valid_coverage": True}


def test_gap_records_survive_restart_and_resolved_gaps_are_not_reselected(tmp_path):
    store = RunStore(tmp_path / "state.sqlite"); controller = RunController(store, TestAutomationObjectiveAdapter()); controller.start("ta", manifest())
    workflow = TestAutomationWorkflow(controller); key = ActionKey("TEST", "app/user.py", "L1", "one")
    workflow.record_measurement("ta", key, measurement([12], [[20, 21]]))
    selected = controller.adapter.select_persisted_gap(store.objective_records("ta")); assert selected["type"] == "uncovered_branch"
    workflow.record_attempt("ta", selected["id"])
    workflow.record_measurement("ta", key, measurement([12], []))
    gaps = [record["payload"]["gaps"] for record in store.objective_records("ta") if record["record_type"] == "test_gaps"][-1]
    assert next(gap for gap in gaps if gap["id"] == selected["id"])["status"] == "resolved"
    assert controller.adapter.select_persisted_gap(store.objective_records("ta"))["type"] == "uncovered_line"
    store.close()


def test_candidate_failure_fingerprint_and_checkpoint_mismatch_use_shared_lifecycle(tmp_path):
    store = RunStore(tmp_path / "state.sqlite"); controller = RunController(store, TestAutomationObjectiveAdapter()); controller.start("ta", manifest())
    workflow = TestAutomationWorkflow(controller); key = ActionKey("TEST", "app/user.py", "L1", "one")
    data = measurement([12], []); data["repository_fingerprint"] = "before"; workflow.record_measurement("ta", key, data)
    candidate = workflow.validate_candidate("ta", key, manifest(), {"gap_id": "line:app/user.py:12", "files": ["app/user.py"], "intent": "bad", "patch": "", "assumptions": [], "expected_evidence": {}}, validation_category="DISALLOWED_CHANGE")
    assert not candidate["valid"] and store.load("ta")["state"]["failure_fingerprints"]
    assert not workflow.reconcile_repository("ta", "after")
    assert controller.recover("ta") == "reconcile_repository"
    store.close()
