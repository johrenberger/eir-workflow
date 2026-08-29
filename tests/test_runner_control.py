from pathlib import Path
from types import SimpleNamespace
from eir_runtime import ResearchController, RunStore, load_eir
from eir_runtime.adapters import RetrievedSource
from eir_runtime.runner import RoutePolicy, OfficialFomcRoutePolicy, run_routes

FIXTURE=Path(__file__).parents[1] / "fixtures" / "domain3.yaml"
TEXT="The Committee decided to maintain the target range for the federal funds rate at 4 to 4-1/4 percent."
class Policy(RoutePolicy):
    def changed_route(self, route, claim_ids): return route + "-changed"
class Flaky:
    def __init__(self): self.calls=[]
    def __call__(self, route):
        self.calls.append(route)
        if route == "statement": raise LookupError("missing")
        return RetrievedSource(route,route,TEXT,"Fed","official_fomc_statement",route)
def test_runner_retries_then_executes_deterministic_l3_route_change(tmp_path):
    store=RunStore(tmp_path/"state.sqlite"); c=ResearchController(store,load_eir(FIXTURE)); c.start("r"); c.plan_universe("r",[{"date":"2025-01-01"}]); f=Flaky(); hooks=[]
    route=SimpleNamespace(date="2025-01-01",statement_url="statement",implementation_url="implementation")
    run_routes(c,"r",[route],f,route_policy=Policy(),retry_hook=hooks.append)
    assert f.calls == ["statement","statement","statement-changed","implementation"] and hooks == [1]
    assert c.status("r")["progress"]["required_fact_coverage"] == 1.0
    store.close()
def test_official_policy_only_returns_same_date_official_implementation_route():
    policy=OfficialFomcRoutePolicy()
    assert policy.changed_route("https://www.federalreserve.gov/newsevents/pressreleases/monetary20250129a.htm",[]) == "https://www.federalreserve.gov/newsevents/pressreleases/monetary20250129a1.htm"
    assert policy.changed_route("https://www.federalreserve.gov/newsevents/pressreleases/monetary20250129a1.htm",[]) == "https://www.federalreserve.gov/monetarypolicy/fomcminutes20250129.htm"
    assert policy.changed_route("https://example.test/newsevents/pressreleases/monetary20250129a.htm",[]) is None
    assert policy.changed_route("https://www.federalreserve.gov/monetarypolicy/fomcminutes20250129.htm",[]) is None
