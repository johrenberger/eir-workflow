from __future__ import annotations
import hashlib, json
import re
from .adapters import RetrievedSource, RetrievalAdapter, ExtractionAdapter, InterpretationAdapter
from .store import RunStore
from .core import ActionKey, RunLifecycle, RunController, TerminalOutcome
from .research_adapter import ResearchObjectiveAdapter
from .evidence import evaluate, independence, progress, changed

class ResearchController:
    def __init__(self, store: RunStore, eir: dict, retrieval: RetrievalAdapter | None = None, extractor: ExtractionAdapter | None = None, interpreter: InterpretationAdapter | None = None):
        self.store, self.eir, self.retrieval, self.extractor, self.interpreter = store, eir, retrieval, extractor, interpreter
        self.lifecycle = RunLifecycle(store)
        self.adapter = ResearchObjectiveAdapter()
        self.run_controller = RunController(store, self.adapter)
    def start(self, run_id: str) -> None:
        self.run_controller.start(run_id, self.eir)
    def dispatch(self, run_id: str, action_class: str, *, ambiguity: bool=False) -> None:
        """Explicit action gate: D1 never invokes a model; N1 is bounded."""
        if action_class not in {"D1", "D2", "N1", "H1"}: raise ValueError("unknown action")
        if action_class == "N1" and not ambiguity: raise ValueError("N1 requires ambiguity or contradiction predicate")
        if action_class == "H1": raise ValueError("use escalate_h1 with a bounded unresolved claim")
        self.store.action(run_id, f"DISPATCH:{action_class}", "OK", {})
    def plan_universe(self, run_id: str, meetings: list[dict]) -> None:
        unique = {str(x["date"]): {"date": str(x["date"]), "provenance": x.get("provenance", "schedule")} for x in meetings}
        with self.store.checkpoint(run_id, "PLANNED") as s:
            s["meeting_universe"] = [unique[k] for k in sorted(unique)]
            s["required_claims"] = [{"id": f"{m['date']}:{field}", "meeting": m["date"], "field": field, "status": "unresolved"} for m in s["meeting_universe"] for field in ("direction", "resulting_range")]
            self._derive(s)
        self.store.action(run_id, "A01-A02", "OK", {"meetings": len(unique)})
    def save_routes(self, run_id: str, routes: list[dict]) -> None:
        """Persist official retrieval routes before their external work begins."""
        with self.store.checkpoint(run_id, "PLANNED") as s:
            if s["route_manifest"] and s["route_manifest"] != routes: raise ValueError("meeting route manifest changed during run")
            s["route_manifest"] = routes
    def ingest(self, run_id: str, source: RetrievedSource) -> str:
        identity = source.canonical_id; digest = hashlib.sha256(source.content.encode()).hexdigest()
        row = self.store.conn.execute("SELECT identity FROM sources WHERE run_id=? AND (identity=? OR hash=?)", (run_id, identity, digest)).fetchone()
        self.store.artifact(digest, source.content)
        self.store.conn.execute("INSERT OR IGNORE INTO sources VALUES (?,?,?,?)", (run_id, identity, digest, json.dumps(source.__dict__))); self.store.conn.commit()
        with self.store.checkpoint(run_id, "EXECUTING") as s:
            s["source_registry"][identity] = {"content_hash": digest, "publisher": source.publisher, "source_class": source.source_class, "provenance_family": source.provenance_family}
            s["retrieval_history"].append({"identity": identity, "deduplicated": bool(row), "available": source.available, "content_hash": digest})
        return row["identity"] if row else identity
    def retrieve(self, run_id: str, route: str) -> RetrievedSource | None:
        if not self.retrieval: raise RuntimeError("retrieval adapter required")
        self.store.action(run_id, f"RETRIEVE:{route}", "INFLIGHT", {"route": route})
        try:
            source = self.retrieval.retrieve(route)
        except Exception as exc:
            self.record_failure(run_id, "A03", route, type(exc).__name__)
            with self.store.checkpoint(run_id, "EXECUTING") as s: s["uncertainties"].append({"class": "temporary_retrieval_unavailability", "route": route})
            return None
        if not source.available:
            self.record_failure(run_id, "A03", route, "SOURCE_UNAVAILABLE")
            with self.store.checkpoint(run_id, "EXECUTING") as s: s["uncertainties"].append({"class": "temporary_retrieval_unavailability", "route": route})
            return None
        self.ingest(run_id, source); self.store.action(run_id, f"RETRIEVE:{route}", "OK", {"identity": source.canonical_id}); return source
    def extract_and_link(self, run_id: str, source: RetrievedSource, polarity: str="support") -> None:
        if not self.extractor: raise RuntimeError("D2 requires extraction adapter")
        try: payload = self.extractor.extract(source)
        except Exception as exc: self.record_failure(run_id, "A04", "extract", type(exc).__name__); return
        self.link_extraction(run_id, source, payload, polarity)
    def link_extraction(self, run_id: str, source: RetrievedSource, payload: dict, polarity: str="support") -> None:
        required = {"meeting_date", "field", "value", "statement_span"}
        normalized_source = re.sub(r"\s+", " ", source.content).replace("‑", "-").replace("–", "-")
        normalized_span = re.sub(r"\s+", " ", payload.get("statement_span", "")).replace("‑", "-").replace("–", "-")
        if not required <= set(payload) or normalized_span not in normalized_source: self.record_failure(run_id, "A04", "extract", "INVALID_EXTRACTION"); return
        claim_id = f"{payload['meeting_date']}:{payload['field']}"
        source_id = self.ingest(run_id, source)
        with self.store.checkpoint(run_id, "EXECUTING") as s:
            if claim_id not in {c['id'] for c in s['required_claims']}: raise ValueError("out-of-universe extraction")
            link = {"source": source_id, "value": payload["value"], "polarity": polarity, "span": payload["statement_span"], "authority": source.source_class.startswith("official"), "family": source.provenance_family}
            link["quality"] = evaluate(link)
            s["claim_evidence_map"].setdefault(claim_id, []).append(link)
            s.setdefault("extraction_records", []).append({"claim": claim_id, "source": source_id, "valid": True})
            self._derive(s)
        self.store.action(run_id, "A04", "OK", {"claim": claim_id})
    def record_failure(self, run_id: str, action: str, route: str, signature: str, strategy: str="L1", claim_id: str | None=None) -> None:
        fp = {"action_id": action, "claim_id": claim_id, "source_identity_or_route": route, "normalized_error_or_conflict_signature": signature, "strategy_id": strategy}
        self.lifecycle.record_failure(
            run_id,
            ActionKey(action, claim_id or route, strategy, route),
            signature=signature,
            phase="EXECUTING",
            payload=fp,
        )
    def can_retry(self, run_id: str, signature: str, strategy: str, changed: bool=False) -> bool:
        s = self.store.load(run_id)["state"]
        return self.lifecycle.can_retry(s["failure_fingerprints"], signature=signature, strategy=strategy, material_change=changed)
    def control_route(self, run_id: str, claim_id: str, signature: str, strategy: str, *, material_change: bool=False) -> str:
        """Apply the EIR's bounded retry policy without performing the next side effect."""
        state = self.store.load(run_id)["state"]
        limits = self.eir["environment"]["execution_limits"]
        unresolved_n1 = any(x["claim_id"] == claim_id and x["unresolved"] for x in state.get("n1_records", []))
        route = self.run_controller.control_route(
            run_id, ActionKey("CONTROL", claim_id, strategy, signature), signature=signature,
            max_attempts_per_strategy=int(limits["max_attempts_per_claim_and_strategy"]),
            max_total_attempts=int(limits["max_total_retrieval_attempts_per_claim"]),
            max_l4_attempts=int(limits.get("max_adjudication_attempts_per_material_contradiction", 2)),
            material_change=material_change, requires_human=unresolved_n1,
        )
        fingerprints = [x for x in state["failure_fingerprints"] if x.get("claim_id") == claim_id]
        same = [x for x in fingerprints if x["strategy_id"] == strategy and x["normalized_error_or_conflict_signature"] == signature]
        total = len(fingerprints)
        with self.store.checkpoint(run_id, "EXECUTING") as updated:
            updated["strategy_history"].append({"claim_id": claim_id, "from": strategy, "signature": signature, "decision": route, "material_change": material_change, "attempt_count": len(same), "total_attempt_count": total})
        return route
    def replan(self, run_id: str, signature: str, strategy: str, *, material_change: bool=False) -> str:
        state = self.store.load(run_id)["state"]
        level = self.lifecycle.next_strategy(state["failure_fingerprints"], signature=signature, strategy=strategy, material_change=material_change)
        with self.store.checkpoint(run_id, "EXECUTING") as s:
            s["strategy_history"].append({"from": strategy, "to": level, "signature": signature, "material_change": material_change})
        return level
    def record_schema_pressure(self, run_id: str, concept: str, gap: str) -> None:
        if concept not in {"claim", "source", "citation", "hypothesis"}: raise ValueError("unknown schema pressure concept")
        with self.store.checkpoint(run_id, "EXECUTING") as s:
            s["schema_pressure_log"].append({"candidate_concept": concept, "observed_gap": gap, "disposition": "record_for_post_test_review"})
    def n1_context(self, run_id: str, claim_id: str) -> dict:
        links = self.store.load(run_id)["state"]["claim_evidence_map"].get(claim_id, [])
        if len({x["polarity"] for x in links}) < 2: raise ValueError("N1 requires conflicting evidence")
        return {"claim_id": claim_id, "evidence": links, "unresolved": True}
    def interpret_n1(self, run_id: str, claim_id: str) -> dict:
        if not self.interpreter: raise RuntimeError("N1 requires an interpretation adapter")
        self.dispatch(run_id, "N1", ambiguity=True)
        context = self.n1_context(run_id, claim_id)
        result = self.interpreter.interpret(context)
        if not isinstance(result, dict) or result.get("resolution") not in {"ambiguous", "needs_adjudication"} or not isinstance(result.get("rationale"), str):
            self.record_failure(run_id, "A07", claim_id, "INVALID_N1_OUTPUT")
            raise ValueError("invalid bounded N1 output")
        record = {"claim_id": claim_id, "context_evidence_count": len(context["evidence"]), "resolution": result["resolution"], "rationale": result["rationale"], "unresolved": True}
        with self.store.checkpoint(run_id, "EXECUTING") as state:
            state["n1_records"].append(record)
            state["uncertainties"].append({"class": "conflicting_claim_evidence", "claim_id": claim_id})
        self.store.action(run_id, "A07", "UNRESOLVED", record)
        return record
    def adjudicate_l4(self, run_id: str, claim_id: str, source: RetrievedSource, payload: dict, *, resolution: str) -> None:
        """Resolve a conflict only with a separately routed official artifact."""
        if resolution not in {"support", "refute"}: raise ValueError("invalid adjudication resolution")
        context = self.n1_context(run_id, claim_id)
        existing_families = {x.get("family") for x in context["evidence"]}
        if not source.source_class.startswith("official") or source.provenance_family in existing_families:
            raise ValueError("L4 requires a distinct authoritative provenance family")
        self.link_extraction(run_id, source, payload, resolution)
        with self.store.checkpoint(run_id, "EXECUTING") as state:
            state["adjudications"][claim_id] = {"resolution": resolution, "source": source.canonical_id, "family": source.provenance_family, "method": "L4_distinct_authoritative_route"}
            self._derive(state)
        self.store.action(run_id, "A08", "ADJUDICATED", state["adjudications"][claim_id])
    def escalate_h1(self, run_id: str, claim_id: str, *, exhausted: bool) -> dict:
        """Durable stop boundary after bounded N1/L4 cannot resolve a material conflict."""
        state = self.store.load(run_id)["state"]
        if not exhausted: raise ValueError("H1 requires bounded exhaustion")
        if claim_id in state.get("adjudications", {}): raise ValueError("adjudicated claim cannot be handed off")
        if not any(x["claim_id"] == claim_id and x["unresolved"] for x in state.get("n1_records", [])): raise ValueError("H1 requires unresolved N1 record")
        prior = [x for x in state.get("human_handoffs", []) if x["claim_id"] == claim_id]
        if prior: return prior[0]
        context = self.n1_context(run_id, claim_id)
        record = {"claim_id": claim_id, "reason": "unresolved_material_ambiguity_after_bounded_N1_L4", "evidence": context["evidence"],
                  "failure_fingerprints": [x for x in state["failure_fingerprints"] if x.get("claim_id") in {None, claim_id}], "immutable": True}
        with self.store.checkpoint(run_id, "HANDOFF") as updated: updated["human_handoffs"].append(record)
        self.store.action(run_id, "H1", "HANDOFF", record)
        return record
    def resolve_h1(self, run_id: str, claim_id: str, *, operator: str, rationale: str, next_strategy: str) -> dict:
        """Human authority may reopen research, but never inject an unverified fact."""
        if not operator.strip() or not rationale.strip() or not next_strategy.strip(): raise ValueError("operator, rationale, and next strategy are required")
        state = self.store.load(run_id)["state"]
        if self.store.load(run_id)["phase"] != "HANDOFF": raise ValueError("run is not awaiting human handoff")
        if not any(x["claim_id"] == claim_id for x in state.get("human_handoffs", [])): raise ValueError("no matching handoff")
        record = {"claim_id": claim_id, "operator": operator, "rationale": rationale, "next_strategy": next_strategy, "injects_fact": False}
        with self.store.checkpoint(run_id, "EXECUTING") as updated: updated["human_resolutions"].append(record)
        self.store.action(run_id, "H1", "RESOLVED", record)
        return record
    def recover(self, run_id: str) -> str | None:
        """Select, rather than duplicate, the smallest durable incomplete action."""
        return self.run_controller.recover(run_id)
    def independently_verify(self, run_id: str, claim_id: str, source: RetrievedSource) -> None:
        with self.store.checkpoint(run_id, "EXECUTING") as s:
            links=s["claim_evidence_map"].get(claim_id, []); ok=bool(links and any(x["source"] != source.canonical_id for x in links))
            s["independent_verification_records"].append({"claim": claim_id, "source": source.canonical_id, "verified": ok})
    def complete(self, run_id: str, exhausted: bool=False) -> TerminalOutcome:
        return self.run_controller.complete(run_id, exhausted=exhausted)
    def status(self, run_id: str) -> dict:
        r=self.store.load(run_id); s=r["state"]; return {"run_id":run_id,"phase":r["phase"],"terminal_outcome":r["terminal"],"reason_code":r["reason"],"required_claims":len(s["required_claims"]),"supported_claims":s["supported_claims"],"unsupported_claims":s["unsupported_claims"],"contradicted_claims":s["contradicted_claims"],"progress":s["progress_metrics"],"failure_fingerprints":s["failure_fingerprints"],"verification_complete":len({x['claim'] for x in s['independent_verification_records'] if x['verified']})==len(s["required_claims"])}
    @staticmethod
    def _derive(s: dict) -> None:
        ResearchObjectiveAdapter().derive(s)
