from pathlib import Path
from types import SimpleNamespace
from eir_runtime import ResearchController, RunStore, load_eir
from eir_runtime.adapters import RetrievedSource
from eir_runtime.runner import run_routes

FIXTURE=Path(__file__).parents[1] / "fixtures" / "domain3.yaml"
TEXT="The Committee decided to maintain the target range for the federal funds rate at 4 to 4-1/4 percent."
class CountingRetrieval:
    def __init__(self): self.calls=[]
    def __call__(self, route):
        self.calls.append(route); return RetrievedSource(route,route,TEXT,"Federal Reserve","official_fomc_statement",route)

def test_interrupted_mocked_route_loop_resumes_without_duplicate_completed_meeting(tmp_path):
    db=tmp_path/"state.sqlite"; routes=[SimpleNamespace(date="2025-01-01",statement_url="s1",implementation_url="i1"),SimpleNamespace(date="2025-02-01",statement_url="s2",implementation_url="i2")]
    first=ResearchController(RunStore(db),load_eir(FIXTURE)); first.start("r"); first.plan_universe("r",[{"date":x.date} for x in routes]); first.save_routes("r",[x.__dict__ for x in routes]); retrieve=CountingRetrieval()
    def interrupt(date):
        if date == "2025-02-01": raise RuntimeError("controller interruption")
    try: run_routes(first,"r",routes,retrieve,before_meeting=interrupt)
    except RuntimeError: pass
    assert retrieve.calls == ["s1","i1"]
    first.store.close()
    resumed=ResearchController(RunStore(db),load_eir(FIXTURE)); resumed.start("r"); run_routes(resumed,"r",routes,retrieve)
    assert retrieve.calls == ["s1","i1","s2","i2"]
    assert len(resumed.store.load("r")["state"]["supported_claims"]) == 4
    resumed.store.close()
