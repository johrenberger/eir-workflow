"""Machine-readable, secret-safe observability artifacts."""
from __future__ import annotations
from datetime import datetime, timezone

STATUS_VERSION = "1.0"

def audit_bundle(store, controller, run_id: str) -> dict:
    run = store.load(run_id); state = run["state"]
    claims = []
    for claim in state["required_claims"]:
        links = state["claim_evidence_map"].get(claim["id"], [])
        claims.append({"claim_id": claim["id"], "meeting": claim["meeting"], "field": claim["field"], "status": claim["status"],
                       "evidence": [{k: link.get(k) for k in ("source", "value", "polarity", "span", "authority", "family", "quality")} for link in links],
                       "independent_verification": [x for x in state["independent_verification_records"] if x["claim"] == claim["id"]]})
    return {"contract_version": STATUS_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(), "status": controller.status(run_id),
            "terminal": {"outcome": run["terminal"], "reason_code": run["reason"], "independently_verified": controller.status(run_id)["verification_complete"]},
            "claims": claims, "source_registry": state.get("source_registry", {}), "uncertainties": state.get("uncertainties", []), "failure_fingerprints": state.get("failure_fingerprints", []), "schema_pressure_log": state.get("schema_pressure_log", []), "human_handoffs": state.get("human_handoffs", []), "human_resolutions": state.get("human_resolutions", [])}
