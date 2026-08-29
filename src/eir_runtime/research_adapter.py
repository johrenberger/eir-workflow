"""Research-domain semantics behind the generic EIR run controller."""
from __future__ import annotations

from .core import TerminalOutcome
from .control import invariant_errors
from .evidence import changed, progress
from .validation import validate_eir
from .verifier import verify


class ResearchObjectiveAdapter:
    def validate_contract(self, eir: dict):
        return validate_eir(eir)

    def derive(self, state: dict) -> None:
        supported, contradicted, unsupported = [], [], []
        for claim in state["required_claims"]:
            links = state["claim_evidence_map"].get(claim["id"], [])
            signs = {link["polarity"] for link in links}
            adjudication = state.get("adjudications", {}).get(claim["id"])
            claim["status"] = (
                "supported" if adjudication and adjudication["resolution"] == "support"
                else "contradicted" if adjudication
                else "contradicted" if len(signs) > 1
                else "supported" if "support" in signs and any(link["authority"] for link in links)
                else "unsupported" if links else "unresolved"
            )
            if claim["status"] == "supported": supported.append(claim["id"])
            elif claim["status"] == "contradicted": contradicted.append(claim["id"])
            else: unsupported.append(claim["id"])
        state["supported_claims"], state["contradicted_claims"], state["unsupported_claims"] = supported, contradicted, unsupported
        state["progress_metrics"] = progress(state)

    def compare(self, before: dict | None, after: dict) -> dict:
        baseline = before or {"required_fact_coverage": 0.0, "authoritative_source_coverage": 0.0, "unresolved_claim_count": 0, "contradiction_count": 0}
        return {"improved": changed(baseline, after), "reason": "research_metric_delta" if changed(baseline, after) else "no_measurable_improvement"}

    def recovery_unit(self, state: dict, records: list[dict] | None = None) -> str | None:
        for claim in state["required_claims"]:
            if claim["status"] not in {"supported", "contradicted"}:
                return claim["id"]
        return None

    def completion(self, state: dict, records: list[dict] | None = None, *, exhausted: bool) -> tuple[TerminalOutcome, str]:
        self.derive(state)
        return verify(state, exhausted=exhausted, invariant_ok=not invariant_errors(state))
