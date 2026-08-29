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
        return self.adapter.recovery_unit(self.store.load(run_id)["state"])

    def complete(self, run_id: str, *, exhausted: bool) -> TerminalOutcome:
        state = self.store.load(run_id)["state"]
        outcome, reason = self.adapter.completion(state, exhausted=exhausted)
        self.lifecycle.terminal(run_id, outcome, reason)
        return outcome
