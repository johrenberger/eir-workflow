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
    def recovery_unit(self, state):
        return "opaque-unit"
    def completion(self, state, *, exhausted):
        return TerminalOutcome.SUPPORTED, "ADAPTER_COMPLETION"


def test_run_controller_delegates_domain_semantics_without_inspecting_units(tmp_path):
    store = RunStore(tmp_path / "state.sqlite")
    controller = RunController(store, _Adapter())
    controller.start("r", {"valid": True})
    store.action("r", "A01", "INFLIGHT", {"unit": "opaque-unit"})
    assert controller.recover("r") == "opaque-unit"
    assert controller.complete("r", exhausted=False) == TerminalOutcome.SUPPORTED
    assert store.load("r")["terminal"] == "SUPPORTED"
    store.close()
