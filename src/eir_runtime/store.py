from __future__ import annotations
import json, sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

FIELDS = ("meeting_universe", "route_manifest", "required_claims", "supported_claims", "unsupported_claims", "contradicted_claims", "claim_evidence_map", "source_registry", "retrieval_history", "failure_fingerprints", "strategy_history", "independent_verification_records", "schema_pressure_log", "progress_metrics", "extraction_records", "inflight_actions", "uncertainties", "n1_records", "adjudications", "human_handoffs", "human_resolutions")
LEGAL_PHASES = {"NEW": {"PLANNED", "RESEARCHING", "TERMINAL"}, "PLANNED": {"PLANNED", "RESEARCHING", "TERMINAL"}, "RESEARCHING": {"RESEARCHING", "HANDOFF", "TERMINAL"}, "HANDOFF": {"RESEARCHING", "TERMINAL"}, "TERMINAL": set()}

class RunStore:
    def __init__(self, db: str | Path):
        Path(db).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db); self.conn.row_factory = sqlite3.Row
        self.conn.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, phase TEXT NOT NULL, version INTEGER NOT NULL, state TEXT NOT NULL, terminal TEXT, reason TEXT)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS actions (run_id TEXT, action_id TEXT, status TEXT, payload TEXT, PRIMARY KEY(run_id, action_id))")
        self.conn.execute("CREATE TABLE IF NOT EXISTS action_log (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, action_id TEXT, status TEXT, payload TEXT)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS sources (run_id TEXT, identity TEXT, hash TEXT, payload TEXT, PRIMARY KEY(run_id, identity))")
        self.conn.execute("CREATE TABLE IF NOT EXISTS artifacts (hash TEXT PRIMARY KEY, content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        self.conn.commit()
    def close(self) -> None:
        self.conn.close()
    def create(self, run_id: str) -> None:
        state = {k: ([] if k not in {"claim_evidence_map", "source_registry", "progress_metrics", "adjudications"} else {}) for k in FIELDS}
        self.conn.execute("INSERT INTO runs VALUES (?, 'NEW', 0, ?, NULL, NULL)", (run_id, json.dumps(state))); self.conn.commit()
    def load(self, run_id: str) -> dict:
        row = self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row: raise KeyError(run_id)
        return {**dict(row), "state": json.loads(row["state"])}
    @contextmanager
    def checkpoint(self, run_id: str, phase: str) -> Iterator[dict]:
        row = self.load(run_id); state = row["state"]
        if phase not in LEGAL_PHASES.get(row["phase"], set()): raise ValueError(f"illegal transition {row['phase']} -> {phase}")
        try:
            yield state
            self.conn.execute("UPDATE runs SET phase=?, version=?, state=? WHERE id=? AND version=?", (phase, row["version"] + 1, json.dumps(state), run_id, row["version"]))
            if self.conn.total_changes == 0: raise RuntimeError("concurrent state update")
            self.conn.commit()
        except Exception:
            self.conn.rollback(); raise
    def action(self, run_id: str, action_id: str, status: str, payload: dict) -> None:
        self.conn.execute("INSERT OR REPLACE INTO actions VALUES (?,?,?,?)", (run_id, action_id, status, json.dumps(payload))); self.conn.commit()
        self.conn.execute("INSERT INTO action_log(run_id,action_id,status,payload) VALUES (?,?,?,?)", (run_id, action_id, status, json.dumps(payload))); self.conn.commit()
    def terminal(self, run_id: str, outcome: str, reason: str) -> None:
        self.conn.execute("UPDATE runs SET phase='TERMINAL', terminal=?, reason=? WHERE id=?", (outcome, reason, run_id)); self.conn.commit()
    def artifact(self, digest: str, content: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO artifacts(hash,content) VALUES (?,?)", (digest, content)); self.conn.commit()
    def has_artifact(self, digest: str) -> bool:
        return bool(self.conn.execute("SELECT 1 FROM artifacts WHERE hash=?", (digest,)).fetchone())
