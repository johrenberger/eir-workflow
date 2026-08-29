from pathlib import Path
import pytest
from eir_runtime import ResearchController, RunStore, TerminalOutcome, load_eir
from eir_runtime.adapters import FakeInterpreter, RetrievedSource

FIXTURE=Path(__file__).parents[1] / "fixtures" / "domain3.yaml"
def source(i): return RetrievedSource("u"+i,i,"The range is 4.00 to 4.25.","Federal Reserve","official_fomc_statement",i)
def setup(tmp_path, payload):
    s=RunStore(tmp_path/"state.sqlite"); c=ResearchController(s,load_eir(FIXTURE),interpreter=FakeInterpreter(payload)); c.start("r"); c.plan_universe("r",[{"date":"2025-01-01"}]); fact={"meeting_date":"2025-01-01","field":"resulting_range","value":"4.00-4.25","statement_span":"4.00 to 4.25"}; c.link_extraction("r",source("a"),fact,"support"); c.link_extraction("r",source("b"),fact,"refute"); return c,s
def test_ambiguous_n1_does_not_resolve_claim(tmp_path):
    c,s=setup(tmp_path,{"resolution":"ambiguous","rationale":"conflicting direct records"}); result=c.interpret_n1("r","2025-01-01:resulting_range")
    assert result["unresolved"] and "2025-01-01:resulting_range" in s.load("r")["state"]["contradicted_claims"]
    assert c.complete("r",exhausted=True) == TerminalOutcome.INSUFFICIENT_EVIDENCE
def test_n1_rejects_model_asserted_resolution(tmp_path):
    c,s=setup(tmp_path,{"resolution":"support","rationale":"I prefer this source"})
    with pytest.raises(ValueError): c.interpret_n1("r","2025-01-01:resulting_range")
    assert not s.load("r")["state"]["n1_records"]
