"""Domain-neutral lifecycle primitives for EIR runs.

These operations deliberately treat unit identifiers and fingerprints as opaque.
Domain adapters decide what a unit represents and how to assess it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .store import RunStore


@dataclass(frozen=True)
class ActionKey:
    action_id: str
    unit_id: str | None
    strategy_id: str
    input_fingerprint: str


class TerminalOutcome(StrEnum):
    SUPPORTED = "SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAILED = "FAILED"


class RunLifecycle:
    """Durable, domain-neutral action and retry lifecycle over ``RunStore``."""

    def __init__(self, store: RunStore):
        self.store = store

    def record_failure(self, run_id: str, key: ActionKey, *, signature: str, phase: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        fingerprint = {
            "action_id": key.action_id,
            "unit_id": key.unit_id,
            "input_fingerprint": key.input_fingerprint,
            "normalized_error_or_conflict_signature": signature,
            "strategy_id": key.strategy_id,
        }
        if payload:
            fingerprint.update(payload)
        with self.store.checkpoint(run_id, phase) as state:
            state["failure_fingerprints"].append(fingerprint)
        self.store.action(run_id, key.action_id, "INVALID", fingerprint)
        return fingerprint

    @staticmethod
    def can_retry(fingerprints: list[dict[str, Any]], *, signature: str, strategy: str, max_attempts: int = 2, material_change: bool = False) -> bool:
        same = [item for item in fingerprints if item.get("normalized_error_or_conflict_signature") == signature and item.get("strategy_id") == strategy]
        if strategy == "L3":
            return material_change and len(same) < max_attempts
        return len(same) < max_attempts

    @staticmethod
    def next_strategy(fingerprints: list[dict[str, Any]], *, signature: str, strategy: str, material_change: bool = False, max_attempts: int = 2) -> str:
        """Select a bounded opaque strategy without inspecting a domain unit."""
        if strategy == "L3" and not material_change:
            raise ValueError("L3 requires a material source/path/context change")
        same = [item for item in fingerprints if item.get("normalized_error_or_conflict_signature") == signature and item.get("strategy_id") == strategy]
        return strategy if len(same) < max_attempts else "L3"

    def reconcile_inflight(self, run_id: str) -> list[dict[str, Any]]:
        pending = self.store.conn.execute(
            "SELECT action_id,payload FROM action_log WHERE run_id=? AND status='INFLIGHT' ORDER BY id",
            (run_id,),
        ).fetchall()
        reconciled = []
        for row in pending:
            payload = json.loads(row["payload"])
            self.store.action(run_id, row["action_id"], "RECONCILED", payload)
            reconciled.append({"action_id": row["action_id"], "payload": payload})
        return reconciled

    def terminal(self, run_id: str, outcome: str, reason: str) -> None:
        self.store.terminal(run_id, outcome, reason)


class RunController:
    """Generic run orchestration; adapters provide all domain semantics."""

    def __init__(self, store: RunStore, adapter):
        self.store, self.adapter, self.lifecycle = store, adapter, RunLifecycle(store)

    def start(self, run_id: str, contract: dict) -> None:
        try:
            existing = self.store.load(run_id)
            if existing["terminal"]:
                raise ValueError(f"run already terminal: {existing['terminal']}")
            return
        except KeyError:
            pass
        issues = self.adapter.validate_contract(contract)
        self.store.create(run_id)
        if issues:
            self.store.action(run_id, "VALIDATE", "INVALID", {"diagnostics": [issue.__dict__ for issue in issues]})
            self.lifecycle.terminal(run_id, TerminalOutcome.FAILED, "INVALID_EIR")
            raise ValueError(issues)
        self.store.action(run_id, "VALIDATE", "OK", {})

    def recover(self, run_id: str):
        self.lifecycle.reconcile_inflight(run_id)
        return self.adapter.recovery_unit(self.store.load(run_id)["state"], self.store.objective_records(run_id))

    def record_measurement(self, run_id: str, key: ActionKey, measurement: dict[str, Any]) -> dict[str, Any]:
        """Persist an adapter-assessed measurement without inspecting its domain metrics."""
        self._activate(run_id)
        records = self.store.objective_records(run_id)
        previous = next((record["payload"] for record in reversed(records) if record["record_type"] == "measurement"), None)
        decision = self.adapter.compare(previous, measurement)
        payload = {"action": key.action_id, "unit_id": key.unit_id, "strategy_id": key.strategy_id, "input_fingerprint": key.input_fingerprint, "measurement": measurement, "progress": decision}
        self.store.objective_record(run_id, "measurement", payload)
        self.store.action(run_id, key.action_id, "PROGRESS" if decision["improved"] else "NO_PROGRESS", payload)
        return decision

    def handoff(self, run_id: str, key: ActionKey, *, reason: str, evidence: dict[str, Any]) -> dict[str, Any]:
        """Create one durable L5/H1 boundary for an opaque unresolved unit."""
        self._activate(run_id)
        prior = next((record for record in self.store.objective_records(run_id) if record["record_type"] == "human_handoff" and record["payload"]["unit_id"] == key.unit_id), None)
        if prior:
            return prior["payload"]
        record = {"action": key.action_id, "unit_id": key.unit_id, "strategy_id": "L5", "reason": reason, "evidence": evidence, "immutable": True}
        self.store.objective_record(run_id, "human_handoff", record)
        self.store.action(run_id, "H1", "HANDOFF", record)
        with self.store.checkpoint(run_id, "HANDOFF"):
            pass
        return record

    def resolve_handoff(self, run_id: str, key: ActionKey, *, operator: str, rationale: str, next_strategy: str) -> dict[str, Any]:
        if not operator.strip() or not rationale.strip() or not next_strategy.strip():
            raise ValueError("operator, rationale, and next strategy are required")
        record = {"action": key.action_id, "unit_id": key.unit_id, "operator": operator, "rationale": rationale, "next_strategy": next_strategy, "injects_fact": False}
        self.store.objective_record(run_id, "human_resolution", record)
        self.store.action(run_id, "H1", "RESOLVED", record)
        with self.store.checkpoint(run_id, "EXECUTING"):
            pass
        return record

    def control_route(self, run_id: str, key: ActionKey, *, signature: str, max_attempts_per_strategy: int, max_total_attempts: int, max_l4_attempts: int, material_change: bool = False, requires_human: bool = False) -> str:
        """Generic bounded L1–L4 route selection over opaque units."""
        if key.strategy_id not in {"L1", "L2", "L3", "L4"}:
            raise ValueError("unsupported control strategy")
        fingerprints = [item for item in self.store.load(run_id)["state"]["failure_fingerprints"] if item.get("unit_id", item.get("claim_id")) == key.unit_id]
        same = [item for item in fingerprints if item.get("strategy_id") == key.strategy_id and item.get("normalized_error_or_conflict_signature") == signature]
        if len(fingerprints) >= max_total_attempts:
            decision = "H1" if requires_human else "TERMINAL_ASSESSMENT"
        elif key.strategy_id in {"L1", "L2"} and len(same) < max_attempts_per_strategy:
            decision = f"RETRY_{key.strategy_id}"
        elif key.strategy_id in {"L1", "L2"}:
            decision = "L3"
        elif key.strategy_id == "L3" and not material_change:
            raise ValueError("L3 requires a material source/path/context change")
        elif key.strategy_id == "L3" and len(same) < max_attempts_per_strategy:
            decision = "RETRY_L3"
        elif key.strategy_id == "L3":
            decision = "L4"
        elif len(same) < max_l4_attempts:
            decision = "RETRY_L4"
        else:
            decision = "H1" if requires_human else "TERMINAL_ASSESSMENT"
        self.store.objective_record(run_id, "control_decision", {"key": key.__dict__, "signature": signature, "decision": decision, "material_change": material_change})
        return decision

    def complete(self, run_id: str, *, exhausted: bool) -> TerminalOutcome:
        state = self.store.load(run_id)["state"]
        outcome, reason = self.adapter.completion(state, self.store.objective_records(run_id), exhausted=exhausted)
        self.lifecycle.terminal(run_id, outcome, reason)
        return outcome

    def _activate(self, run_id: str) -> None:
        """Move generic adapter work into a legal durable active phase."""
        phase = self.store.load(run_id)["phase"]
        if phase == "NEW":
            with self.store.checkpoint(run_id, "PLANNED"):
                pass
            phase = "PLANNED"
        if phase == "PLANNED":
            with self.store.checkpoint(run_id, "EXECUTING"):
                pass
