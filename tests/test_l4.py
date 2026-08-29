from pathlib import Path
import pytest
from eir_runtime import ResearchController, RunStore, load_eir
from eir_runtime.adapters import RetrievedSource

FIXTURE=Path(__file__).parents[1] / "fixtures" / "domain3.yaml"
def src(identity, family, kind="official_fomc_statement"):
    return RetrievedSource("u"+identity,identity,"The range is 4.00 to 4.25.","Federal Reserve",kind,family)
def fact(): return {"meeting_date":"2025-01-01","field":"resulting_range","value":"4.00-4.25","statement_span":"4.00 to 4.25"}
def setup(tmp_path):
    s=RunStore(tmp_path/"state.sqlite"); c=ResearchController(s,load_eir(FIXTURE)); c.start("r"); c.plan_universe("r",[{"date":"2025-01-01"}]); c.link_extraction("r",src("official","primary"),fact(),"support"); c.link_extraction("r",src("secondary","derivative","reputable_secondary_reporting"),fact(),"refute"); return c,s
def test_l4_distinct_authoritative_route_resolves_conflict_and_retains_links(tmp_path):
    c,s=setup(tmp_path); c.adjudicate_l4("r","2025-01-01:resulting_range",src("implementation","implementation"),fact(),resolution="support")
    state=s.load("r")["state"]; assert "2025-01-01:resulting_range" in state["supported_claims"]
    assert len(state["claim_evidence_map"]["2025-01-01:resulting_range"]) == 3 and state["adjudications"]["2025-01-01:resulting_range"]["method"] == "L4_distinct_authoritative_route"
def test_l4_rejects_non_distinct_or_non_authoritative_route(tmp_path):
    c,s=setup(tmp_path)
    with pytest.raises(ValueError): c.adjudicate_l4("r","2025-01-01:resulting_range",src("same","primary"),fact(),resolution="support")
    with pytest.raises(ValueError): c.adjudicate_l4("r","2025-01-01:resulting_range",src("not-official","new","reputable_secondary_reporting"),fact(),resolution="support")
