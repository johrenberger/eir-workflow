"""Transparent domain metrics; no model-provided evidence scores."""
from __future__ import annotations
from collections import Counter

METRIC_VERSION = "domain3-v1"

def evaluate(link: dict) -> dict:
    authority = 1.0 if link.get("authority") else 0.2
    directness = 1.0 if link.get("span") else 0.0
    return {"metric_version": METRIC_VERSION, "authority": authority, "directness": directness,
            "independence_family": link.get("family"), "complete": bool(link.get("value")),
            "explanation": "official direct evidence" if authority == 1 else "non-authoritative evidence"}

def independence(links: list[dict]) -> dict:
    families = {x.get("family") for x in links if x.get("family")}
    authoritative = {x.get("family") for x in links if x.get("authority") and x.get("family")}
    return {"independence_families": len(families), "authoritative_families": len(authoritative), "families": sorted(families)}

def progress(state: dict) -> dict:
    claims = state["required_claims"]; total = len(claims)
    supported = [c for c in claims if c["status"] == "supported"]
    contradicted = [c for c in claims if c["status"] == "contradicted"]
    authoritative = sum(bool(any(x.get("authority") for x in state["claim_evidence_map"].get(c["id"], []))) for c in claims)
    return {"metric_version": METRIC_VERSION, "required_fact_coverage": len(supported)/total if total else 0.0,
            "authoritative_source_coverage": authoritative/total if total else 0.0,
            "unresolved_claim_count": total-len(supported)-len(contradicted), "contradiction_count": len(contradicted)}

def changed(before: dict, after: dict) -> bool:
    return any(after[k] > before[k] for k in ("required_fact_coverage", "authoritative_source_coverage")) or any(after[k] < before[k] for k in ("unresolved_claim_count", "contradiction_count"))
