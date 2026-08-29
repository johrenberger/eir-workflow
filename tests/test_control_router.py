from pathlib import Path
import pytest
from eir_runtime import ResearchController, RunStore, load_eir
from eir_runtime.adapters import FakeInterpreter, RetrievedSource

FIXTURE=Path(__file__).parents[1] / "fixtures" / "domain3.yaml"
CLAIM="2025-01-01:resulting_range"
def make(tmp_path):
    s=RunStore(tmp_path/"state.sqlite"); c=ResearchController(s,load_eir(FIXTURE)); c.start("r"); c.plan_universe("r",[{"date":"2025-01-01"}]); return c,s
def fail(c, strategy, n, signature="UNAVAILABLE"):
    for _ in range(n): c.record_failure("r","A03","route",signature,strategy,CLAIM)
def test_per_claim_strategy_budget_routes_l1_to_l3(tmp_path):
    c,s=make(tmp_path); assert c.control_route("r",CLAIM,"UNAVAILABLE","L1") == "RETRY_L1"
    fail(c,"L1",2); assert c.control_route("r",CLAIM,"UNAVAILABLE","L1") == "L3"
def test_l3_requires_material_change_then_routes_to_l4(tmp_path):
    c,s=make(tmp_path); fail(c,"L3",2)
    with pytest.raises(ValueError): c.control_route("r",CLAIM,"UNAVAILABLE","L3")
    assert c.control_route("r",CLAIM,"UNAVAILABLE","L3",material_change=True) == "L4"
def test_l4_exhaustion_routes_to_terminal_assessment_without_n1(tmp_path):
    c,s=make(tmp_path); fail(c,"L4",2); assert c.control_route("r",CLAIM,"CONFLICT","L4") == "RETRY_L4"
    fail(c,"L4",2,"CONFLICT"); assert c.control_route("r",CLAIM,"CONFLICT","L4") == "TERMINAL_ASSESSMENT"
def test_l4_exhaustion_routes_h1_with_unresolved_n1(tmp_path):
    c,s=make(tmp_path); fact={"meeting_date":"2025-01-01","field":"resulting_range","value":"x","statement_span":"range x"}
    for i,p in (("a","support"),("b","refute")): c.link_extraction("r",RetrievedSource("u"+i,i,"range x","Fed","official_fomc_statement",i),fact,p)
    c.interpreter=FakeInterpreter({"resolution":"needs_adjudication","rationale":"conflict"}); c.interpret_n1("r",CLAIM); fail(c,"L4",2,"CONFLICT")
    assert c.control_route("r",CLAIM,"CONFLICT","L4") == "H1"
def test_total_budget_forces_terminal_assessment(tmp_path):
    c,s=make(tmp_path); fail(c,"L1",8); assert c.control_route("r",CLAIM,"UNAVAILABLE","L1") == "TERMINAL_ASSESSMENT"
