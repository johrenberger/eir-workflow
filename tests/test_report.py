from pathlib import Path
from eir_runtime import ResearchController, RunStore, load_eir
from eir_runtime.adapters import RetrievedSource
from eir_runtime.report import audit_bundle

FIXTURE=Path(__file__).parents[1] / "fixtures" / "domain3.yaml"
def test_audit_bundle_is_versioned_claim_level_and_excludes_source_body(tmp_path):
    store=RunStore(tmp_path/"state.sqlite"); c=ResearchController(store,load_eir(FIXTURE)); c.start("r"); c.plan_universe("r",[{"date":"2025-01-01"}])
    text="The range is 4.00 to 4.25. SECRET-BODY"
    source=RetrievedSource("u","official",text,"Federal Reserve","official_fomc_statement","official")
    c.link_extraction("r",source,{"meeting_date":"2025-01-01","field":"resulting_range","value":"4.00-4.25","statement_span":"4.00 to 4.25"})
    bundle=audit_bundle(store,c,"r")
    assert bundle["contract_version"] == "1.0" and len(bundle["claims"]) == 2
    assert "SECRET-BODY" not in str(bundle) and bundle["claims"][1]["evidence"][0]["source"] == "official"
    store.close()
