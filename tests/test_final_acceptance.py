from pathlib import Path
from types import SimpleNamespace
from eir_runtime import ResearchController, RunStore, TerminalOutcome, load_eir, validate_eir
from eir_runtime.adapters import RetrievedSource
from eir_runtime.report import audit_bundle
from eir_runtime.runner import run_routes

ROOT=Path(__file__).parents[1]; EIR=ROOT/"fixtures"/"domain3.yaml"
def test_final_acceptance_gate_offline_eir_lifecycle(tmp_path):
    eir=load_eir(EIR); assert validate_eir(eir) == []
    store=RunStore(tmp_path/"acceptance.sqlite"); c=ResearchController(store,eir); c.start("acceptance")
    route=SimpleNamespace(date="2099-03-01",statement_url="statement",implementation_url="implementation")
    c.plan_universe("acceptance",[{"date":route.date,"provenance":"synthetic-official-calendar"}]); c.save_routes("acceptance",[route.__dict__])
    text="The Committee decided to maintain the target range for the federal funds rate at 3 to 3-1/4 percent."
    def retrieve(url): return RetrievedSource(url,url,text,"Federal Reserve","official_fomc_statement",url)
    run_routes(c,"acceptance",[route],retrieve)
    assert c.complete("acceptance",exhausted=True) == TerminalOutcome.SUPPORTED
    report=audit_bundle(store,c,"acceptance")
    assert report["terminal"]["outcome"] == "SUPPORTED" and len(report["claims"]) == 2 and report["status"]["progress"]["required_fact_coverage"] == 1.0
    store.close()
