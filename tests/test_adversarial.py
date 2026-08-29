"""Domain 3 AT-01 through AT-05: every adverse path must fail closed."""
from pathlib import Path
from eir_runtime import ResearchController, RunStore, TerminalOutcome, load_eir
from eir_runtime.adapters import FakeRetrieval, RetrievedSource
from eir_runtime.evidence import independence
import yaml

FIXTURE=Path(__file__).parents[1] / "fixtures" / "domain3.yaml"
def make(tmp_path):
    s=RunStore(tmp_path/"state.sqlite"); c=ResearchController(s,load_eir(FIXTURE)); c.start("r"); c.plan_universe("r",[{"date":"2025-01-01"}]); return c,s
def src(identity, text="The range is 4.00 to 4.25.", source_class="official_fomc_statement", family=None, available=True):
    return RetrievedSource(f"https://example.test/{identity}",identity,text,"Federal Reserve",source_class,family or identity,available)
def fact(value="4.00-4.25"):
    return {"meeting_date":"2025-01-01","field":"resulting_range","value":value,"statement_span":"4.00 to 4.25"}

def test_at01_missing_authoritative_statement_is_insufficient(tmp_path):
    c,s=make(tmp_path); c.retrieval=FakeRetrieval({}); assert c.retrieve("r","official-route") is None
    assert c.complete("r",exhausted=True) == TerminalOutcome.INSUFFICIENT_EVIDENCE
def test_at02_secondary_contradiction_is_retained_and_blocks_supported(tmp_path):
    c,s=make(tmp_path); c.link_extraction("r",src("official"),fact(),"support"); c.link_extraction("r",src("secondary","The range is 4.00 to 4.25.","reputable_secondary_reporting"),fact(),"refute")
    assert "2025-01-01:resulting_range" in s.load("r")["state"]["contradicted_claims"]
    assert c.complete("r",exhausted=True) == TerminalOutcome.INSUFFICIENT_EVIDENCE
def test_at03_derivative_swarm_has_one_independence_family(tmp_path):
    links=[{"family":"official-upstream","authority":False},{"family":"official-upstream","authority":False},{"family":"official-upstream","authority":False}]
    assert independence(links)["independence_families"] == 1
def test_at04_initial_assumption_is_not_a_claim_or_evidence(tmp_path):
    c,s=make(tmp_path); state=s.load("r")["state"]
    assert not state["claim_evidence_map"] and all("value" not in claim for claim in state["required_claims"])
    c.link_extraction("r",src("official"),fact("evidence-derived"))
    assert s.load("r")["state"]["claim_evidence_map"]["2025-01-01:resulting_range"][0]["value"] == "evidence-derived"
def test_at05_unavailable_source_requires_changed_strategy_after_stagnation(tmp_path):
    c,s=make(tmp_path); unavailable=src("unavailable",available=False); c.retrieval=FakeRetrieval({"route":unavailable})
    assert c.retrieve("r","route") is None; assert c.retrieve("r","route") is None
    assert not c.can_retry("r","SOURCE_UNAVAILABLE","L1")
    assert c.replan("r","SOURCE_UNAVAILABLE","L1") == "L3"
def test_all_adversarial_yaml_fixtures_are_loadable():
    paths=sorted((Path(__file__).parents[1]/"fixtures"/"adversarial").glob("AT-*.yaml"))
    assert [yaml.safe_load(x.read_text())["id"] for x in paths] == [f"AT-0{i}" for i in range(1,6)]
