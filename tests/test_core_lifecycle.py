from eir_runtime import RunStore
from eir_runtime.core import ActionKey, RunController, RunLifecycle, TerminalOutcome


def test_lifecycle_persists_opaque_fingerprint_and_respects_retry_budget(tmp_path):
    store = RunStore(tmp_path / "state.sqlite")
    store.create("r")
    lifecycle = RunLifecycle(store)
    key = ActionKey("A01", "opaque-unit", "L1", "input-hash")
    lifecycle.record_failure("r", key, signature="FAILED", phase="PLANNED")
    lifecycle.record_failure("r", key, signature="FAILED", phase="RESEARCHING")
    fingerprints = store.load("r")["state"]["failure_fingerprints"]
    assert fingerprints[0]["unit_id"] == "opaque-unit"
    assert not lifecycle.can_retry(fingerprints, signature="FAILED", strategy="L1")
    assert not lifecycle.can_retry(fingerprints, signature="FAILED", strategy="L3")
    assert lifecycle.can_retry(fingerprints, signature="FAILED", strategy="L3", material_change=True)
    store.close()


def test_lifecycle_reconciles_inflight_and_writes_terminal_state(tmp_path):
    store = RunStore(tmp_path / "state.sqlite")
    store.create("r")
    store.action("r", "A01", "INFLIGHT", {"opaque": True})
    lifecycle = RunLifecycle(store)
    assert lifecycle.reconcile_inflight("r") == [{"action_id": "A01", "payload": {"opaque": True}}]
    lifecycle.terminal("r", "SUPPORTED", "GENERIC_COMPLETION")
    run = store.load("r")
    assert run["terminal"] == "SUPPORTED" and run["reason"] == "GENERIC_COMPLETION"
    store.close()


class _Adapter:
    def validate_contract(self, contract):
        return [] if contract["valid"] else [type("Issue", (), {"__dict__": {"rule": "X"}})()]
    def recovery_unit(self, state, records):
        return "opaque-unit"
    def completion(self, state, records, *, exhausted):
        return TerminalOutcome.SUPPORTED, "ADAPTER_COMPLETION"
    def compare(self, before, after):
        return {"improved": before is None or after["value"] > before["value"], "reason": "numeric"}


def test_run_controller_delegates_domain_semantics_without_inspecting_units(tmp_path):
    store = RunStore(tmp_path / "state.sqlite")
    controller = RunController(store, _Adapter())
    controller.start("r", {"valid": True})
    store.action("r", "A01", "INFLIGHT", {"unit": "opaque-unit"})
    assert controller.recover("r") == "opaque-unit"
    assert controller.complete("r", exhausted=False) == TerminalOutcome.SUPPORTED
    assert store.load("r")["terminal"] == "SUPPORTED"
    store.close()


def test_generic_control_routing_is_opaque_and_requires_material_l3_change(tmp_path):
    store = RunStore(tmp_path / "state.sqlite")
    controller = RunController(store, _Adapter())
    controller.start("r", {"valid": True})
    key = ActionKey("A01", "opaque-unit", "L1", "input")
    for _ in range(2):
        controller.lifecycle.record_failure("r", key, signature="FAILED", phase="PLANNED")
    assert controller.control_route("r", key, signature="FAILED", max_attempts_per_strategy=2, max_total_attempts=8, max_l4_attempts=2) == "L3"
    l3 = ActionKey("A01", "opaque-unit", "L3", "changed-input")
    try:
        controller.control_route("r", l3, signature="FAILED", max_attempts_per_strategy=2, max_total_attempts=8, max_l4_attempts=2)
    except ValueError as exc:
        assert "material" in str(exc)
    else:
        raise AssertionError("L3 must require a material change")
    assert controller.control_route("r", l3, signature="FAILED", max_attempts_per_strategy=2, max_total_attempts=8, max_l4_attempts=2, material_change=True) == "RETRY_L3"
    store.close()


def test_generic_h1_handoff_is_idempotent_and_requires_human_resolution(tmp_path):
    store = RunStore(tmp_path / "state.sqlite")
    controller = RunController(store, _Adapter())
    controller.start("r", {"valid": True})
    key = ActionKey("A01", "opaque-unit", "L4", "input")
    handoff = controller.handoff("r", key, reason="bounded attempts exhausted", evidence={"fingerprint": "FAILED"})
    assert controller.handoff("r", key, reason="ignored", evidence={}) == handoff
    assert store.load("r")["phase"] == "HANDOFF"
    resolution = controller.resolve_handoff("r", key, operator="operator", rationale="new access", next_strategy="L3")
    assert resolution["injects_fact"] is False and store.load("r")["phase"] == "RESEARCHING"
    store.close()
