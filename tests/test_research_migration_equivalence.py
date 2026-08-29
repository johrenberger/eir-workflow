"""Behavior snapshot for the pre-adapter ResearchController lifecycle."""
from pathlib import Path

from eir_runtime import ResearchController, RunStore, TerminalOutcome, load_eir
from eir_runtime.adapters import RetrievedSource


FIXTURE = Path(__file__).parents[1] / "fixtures" / "domain3.yaml"


def test_research_adapter_preserves_known_state_transition_snapshot(tmp_path):
    store = RunStore(tmp_path / "state.sqlite")
    controller = ResearchController(store, load_eir(FIXTURE))
    controller.start("r")
    controller.plan_universe("r", [{"date": "2025-01-01"}])
    source = RetrievedSource("https://example.test/statement", "statement", "The direction is unchanged. The range is 4.00 to 4.25.", "Federal Reserve", "official_fomc_statement", "statement")
    controller.link_extraction("r", source, {"meeting_date": "2025-01-01", "field": "direction", "value": "unchanged", "statement_span": "direction is unchanged"})
    controller.link_extraction("r", source, {"meeting_date": "2025-01-01", "field": "resulting_range", "value": "4.00-4.25", "statement_span": "range is 4.00 to 4.25"})
    state = store.load("r")["state"]
    assert [(claim["id"], claim["status"]) for claim in state["required_claims"]] == [
        ("2025-01-01:direction", "supported"),
        ("2025-01-01:resulting_range", "supported"),
    ]
    assert state["progress_metrics"] == {"metric_version": "domain3-v1", "required_fact_coverage": 1.0, "authoritative_source_coverage": 1.0, "unresolved_claim_count": 0, "contradiction_count": 0}
    assert controller.complete("r", exhausted=True) == TerminalOutcome.INSUFFICIENT_EVIDENCE
    assert store.load("r")["reason"] == "BOUNDED_EVIDENCE_EXHAUSTED"
    store.close()
