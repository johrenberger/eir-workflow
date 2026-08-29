"""Independent deterministic terminal checker; intentionally does not call controller methods."""
from __future__ import annotations
from .engine import TerminalOutcome

def verify(state: dict, *, exhausted: bool, invariant_ok: bool = True) -> tuple[TerminalOutcome, str]:
    claims = state["required_claims"]
    supported = {c["id"] for c in claims if c["status"] == "supported"}
    contradictory = any(c["status"] == "contradicted" for c in claims)
    verified = {r["claim"] for r in state.get("independent_verification_records", []) if r.get("verified")}
    adequate = all(any(link.get("authority") and link.get("span") for link in state["claim_evidence_map"].get(cid, [])) for cid in supported)
    if not invariant_ok: return TerminalOutcome.FAILED, "STATE_INVARIANT_BREACH"
    if claims and supported == {c["id"] for c in claims} and not contradictory and supported <= verified and adequate:
        return TerminalOutcome.SUPPORTED, "SUFFICIENT_EVIDENCE"
    if exhausted: return TerminalOutcome.INSUFFICIENT_EVIDENCE, "BOUNDED_EVIDENCE_EXHAUSTED"
    return TerminalOutcome.FAILED, "PREMATURE_TERMINATION"
