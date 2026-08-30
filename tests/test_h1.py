from pathlib import Path
import pytest
from eir_runtime import ResearchController, RunStore, load_eir
from eir_runtime.adapters import FakeInterpreter, RetrievedSource

FIXTURE=Path(__file__).parents[1] / "fixtures" / "domain3.yaml"
def setup(tmp_path):
    s=RunStore(tmp_path/"state.sqlite"); c=ResearchController(s,load_eir(FIXTURE),interpreter=FakeInterpreter({"resolution":"needs_adjudication","rationale":"conflict persists"})); c.start("r"); c.plan_universe("r",[{"date":"2025-01-01"}]); fact={"meeting_date":"2025-01-01","field":"resulting_range","value":"x","statement_span":"range is x"};
    for identity, polarity in (("a","support"),("b","refute")):
        c.link_extraction("r",RetrievedSource("u"+identity,identity,"The range is x","Federal Reserve","official_fomc_statement",identity),fact,polarity)
    c.interpret_n1("r","2025-01-01:resulting_range"); return c,s
def test_h1_stops_on_bounded_unresolved_conflict_and_is_idempotent(tmp_path):
    c,s=setup(tmp_path); record=c.escalate_h1("r","2025-01-01:resulting_range",exhausted=True)
    assert s.load("r")["phase"] == "HANDOFF" and record["immutable"]
    assert c.escalate_h1("r","2025-01-01:resulting_range",exhausted=True) == record
def test_h1_requires_bounded_unresolved_n1(tmp_path):
    c,s=setup(tmp_path)
    with pytest.raises(ValueError): c.escalate_h1("r","2025-01-01:resulting_range",exhausted=False)
def test_human_resolution_reopens_without_injecting_fact(tmp_path):
    c,s=setup(tmp_path); handoff=c.escalate_h1("r","2025-01-01:resulting_range",exhausted=True)
    result=c.resolve_h1("r","2025-01-01:resulting_range",operator="reviewer-1",rationale="Use an alternate official archive",next_strategy="L4 alternate archive")
    state=s.load("r")["state"]; assert s.load("r")["phase"] == "EXECUTING" and result["injects_fact"] is False
    assert state["human_handoffs"] == [handoff] and state["human_resolutions"][0]["operator"] == "reviewer-1"
def test_human_resolution_requires_existing_handoff(tmp_path):
    c,s=setup(tmp_path)
    with pytest.raises(ValueError): c.resolve_h1("r","2025-01-01:resulting_range",operator="x",rationale="x",next_strategy="L4")
