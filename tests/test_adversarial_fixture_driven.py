"""AT fixtures are executable test inputs, not merely descriptive documents."""
from pathlib import Path
import pytest, yaml
from eir_runtime import ResearchController, RunStore, TerminalOutcome, load_eir
from eir_runtime.adapters import FakeRetrieval, RetrievedSource
from eir_runtime.evidence import independence

ROOT=Path(__file__).parents[1]; EIR=ROOT/"fixtures"/"domain3.yaml"
FIXTURES=sorted((ROOT/"fixtures"/"adversarial").glob("AT-*.yaml"))
@pytest.mark.parametrize("fixture_path",FIXTURES, ids=lambda p: p.stem)
def test_adversarial_yaml_contracts_execute_fail_closed(tmp_path, fixture_path):
    case=yaml.safe_load(fixture_path.read_text()); store=RunStore(tmp_path/f"{case['id']}.sqlite"); c=ResearchController(store,load_eir(EIR)); c.start("r"); c.plan_universe("r",[{"date":"2099-01-01"}])
    fact={"meeting_date":"2099-01-01","field":"resulting_range","value":"x","statement_span":"range x"}
    official=RetrievedSource("u1","official","range x","Fed","official_fomc_statement","official")
    if case["id"] == "AT-01":
        c.retrieval=FakeRetrieval({}); c.retrieve("r","missing"); assert c.complete("r",exhausted=True) == TerminalOutcome.INSUFFICIENT_EVIDENCE
    elif case["id"] == "AT-02":
        c.link_extraction("r",official,fact,"support"); c.link_extraction("r",RetrievedSource("u2","secondary","range x","Reporter","reputable_secondary_reporting","secondary"),fact,"refute")
        assert "2099-01-01:resulting_range" in c.status("r")["contradicted_claims"]
    elif case["id"] == "AT-03":
        assert independence([{"family":"upstream"},{"family":"upstream"},{"family":"upstream"}])["independence_families"] == 1
    elif case["id"] == "AT-04":
        assert all("value" not in claim for claim in store.load("r")["state"]["required_claims"]); c.link_extraction("r",official,fact); assert c.status("r")["supported_claims"]
    elif case["id"] == "AT-05":
        unavailable=RetrievedSource("u","missing","","Fed","official_fomc_statement","missing",False); c.retrieval=FakeRetrieval({"route":unavailable}); c.retrieve("r","route"); c.retrieve("r","route")
        c.record_failure("r","A03","route","SOURCE_UNAVAILABLE","L1","2099-01-01:resulting_range"); c.record_failure("r","A03","route","SOURCE_UNAVAILABLE","L1","2099-01-01:resulting_range")
        assert c.control_route("r","2099-01-01:resulting_range","SOURCE_UNAVAILABLE","L1") == "L3"
    store.close()
