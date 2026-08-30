"""Research-domain invariants."""
from __future__ import annotations

def invariant_errors(state: dict) -> list[str]:
    required = {c.get("id") for c in state.get("required_claims", [])}
    linked = set(state.get("claim_evidence_map", {}))
    errors = []
    if not linked <= required: errors.append("evidence_link_for_unknown_claim")
    if len(required) != len(state.get("required_claims", [])): errors.append("duplicate_required_claim")
    if any(not c.get("meeting") for c in state.get("required_claims", [])): errors.append("claim_missing_meeting")
    return errors
