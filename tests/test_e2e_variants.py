from pathlib import Path
from types import SimpleNamespace
import yaml
from eir_runtime import ResearchController, RunStore, load_eir
from eir_runtime.adapters import RetrievedSource
from eir_runtime.runner import run_routes

ROOT=Path(__file__).parents[1]; EIR=ROOT/"fixtures"/"domain3.yaml"
def test_synthetic_e2e_variants_are_evidence_derived_not_2025_answer_bearing(tmp_path):
    variants=yaml.safe_load((ROOT/"fixtures"/"e2e"/"synthetic-variants.yaml").read_text())["variants"]
    assert all("2025" not in item["text"] for item in variants)
    for item in variants:
        store=RunStore(tmp_path/f"{item['id']}.sqlite"); controller=ResearchController(store,load_eir(EIR)); controller.start("r")
        route=SimpleNamespace(date=item["date"],statement_url="statement",implementation_url="implementation")
        controller.plan_universe("r",[{"date":item["date"]}])
        def retrieve(url, item=item): return RetrievedSource(url,url,item["text"],"Federal Reserve","official_fomc_statement",url)
        run_routes(controller,"r",[route],retrieve)
        assert len(controller.status("r")["supported_claims"]) == 2
        store.close()
