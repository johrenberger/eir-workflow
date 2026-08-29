"""Bounded retry and escalation policy for Domain 3."""
from __future__ import annotations

def next_level(fingerprints: list[dict], signature: str, strategy: str, *, material_change: bool=False) -> str:
    same = [x for x in fingerprints if x.get("normalized_error_or_conflict_signature") == signature and x.get("strategy_id") == strategy]
    if strategy == "L3" and not material_change: raise ValueError("L3 requires a material source/path/context change")
    if len(same) < 2: return strategy
    return "L3"

def invariant_errors(state: dict) -> list[str]:
    required = {c.get("id") for c in state.get("required_claims", [])}
    linked = set(state.get("claim_evidence_map", {}))
    errors = []
    if not linked <= required: errors.append("evidence_link_for_unknown_claim")
    if len(required) != len(state.get("required_claims", [])): errors.append("duplicate_required_claim")
    if any(not c.get("meeting") for c in state.get("required_claims", [])): errors.append("claim_missing_meeting")
    return errors
