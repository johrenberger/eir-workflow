"""Thin Test Automation composition over the shared EIR controller."""
from __future__ import annotations

from .core import ActionKey, RunController
from .test_generation import proposal_fingerprint, validate_proposal


class TestAutomationWorkflow:
    """Adapter composition only; lifecycle, retry, recovery, and terminal writes stay generic."""

    __test__ = False

    def __init__(self, controller: RunController):
        self.controller = controller
        self.adapter = controller.adapter

    def record_measurement(self, run_id: str, key: ActionKey, measurement: dict) -> dict:
        decision = self.controller.record_measurement(run_id, key, measurement)
        gaps = self.adapter.reconcile_gaps(self.controller.store.objective_records(run_id), measurement)
        self.controller.store.objective_record(run_id, "test_gaps", {"gaps": gaps})
        return decision

    def validate_candidate(self, run_id: str, key: ActionKey, manifest: dict, proposal: dict, *, validation_category: str) -> dict:
        gaps = self.adapter.select_persisted_gap(self.controller.store.objective_records(run_id))
        all_gaps = next((record["payload"]["gaps"] for record in reversed(self.controller.store.objective_records(run_id)) if record["record_type"] == "test_gaps"), [])
        errors = validate_proposal(proposal, manifest, all_gaps)
        fingerprint = proposal_fingerprint(proposal, validation_category=validation_category, strategy=key.strategy_id)
        payload = {"proposal_hash": fingerprint, "validation_category": validation_category, "errors": errors, "selected_gap": gaps["id"] if gaps else None}
        self.controller.store.objective_record(run_id, "test_candidate", payload, fingerprint)
        if errors:
            self.controller.lifecycle.record_failure(run_id, key, signature=validation_category, phase="EXECUTING", payload=payload)
        return {"valid": not errors, **payload}

    def record_attempt(self, run_id: str, gap_id: str) -> None:
        records = self.controller.store.objective_records(run_id)
        latest = next((record["payload"] for record in reversed(records) if record["record_type"] == "test_gaps"), None)
        if not latest:
            raise ValueError("no durable test gaps")
        gaps = [{**gap, "attempts": gap.get("attempts", 0) + (gap["id"] == gap_id)} for gap in latest["gaps"]]
        self.controller.store.objective_record(run_id, "test_gaps", {"gaps": gaps})

    def reconcile_repository(self, run_id: str, current_fingerprint: str) -> bool:
        records = self.controller.store.objective_records(run_id)
        measurements = [record["payload"]["measurement"] for record in records if record["record_type"] == "measurement"]
        expected = measurements[-1].get("repository_fingerprint") if measurements else None
        if expected is None or expected == current_fingerprint:
            return True
        self.controller.store.objective_record(run_id, "repository_mismatch", {"expected": expected, "observed": current_fingerprint})
        return False
