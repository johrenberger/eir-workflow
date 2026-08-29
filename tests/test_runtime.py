from pathlib import Path
import pytest
from eir_runtime import ResearchController, RunStore, TerminalOutcome, load_eir, validate_eir
from eir_runtime.adapters import FakeExtractor, FakeRetrieval, RetrievedSource
from eir_runtime.planner import discover_2025_routes, extract_bounded_facts

FIXTURE=Path(__file__).parents[1] / "fixtures" / "domain3.yaml"

def source(identity="official-1", text="The range is 4.00 to 4.25."):
    return RetrievedSource("https://example.test/x",identity,text,"Federal Reserve","official_fomc_statement",identity)

def controller(tmp_path, payload=None):
    store=RunStore(tmp_path / "state.sqlite"); c=ResearchController(store,load_eir(FIXTURE),extractor=FakeExtractor(payload or {"meeting_date":"2025-01-01","field":"resulting_range","value":"4.00-4.25","statement_span":"4.00 to 4.25"})); c.start("r"); return c,store

def test_v001_to_v020_fixture_passes(): assert validate_eir(load_eir(FIXTURE)) == []
def test_invalid_eir_fails_closed(tmp_path):
    eir=load_eir(FIXTURE); eir["policy"]={}; s=RunStore(tmp_path/"x.sqlite"); c=ResearchController(s,eir)
    with pytest.raises(ValueError): c.start("r")
    assert s.load("r")["terminal"] == "FAILED"
def test_universe_creates_two_claims_per_deduplicated_meeting(tmp_path):
    c,s=controller(tmp_path); c.plan_universe("r",[{"date":"2025-01-01"},{"date":"2025-01-01"}]); assert len(s.load("r")["state"]["required_claims"]) == 2
def test_malformed_extraction_is_rejected(tmp_path):
    c,s=controller(tmp_path,payload="not json"); c.plan_universe("r",[{"date":"2025-01-01"}]); c.extract_and_link("r",source()); assert not s.load("r")["state"]["claim_evidence_map"]
def test_source_identity_deduplicates(tmp_path):
    c,s=controller(tmp_path); assert c.ingest("r",source()) == "official-1"; assert c.ingest("r",source()) == "official-1"; assert s.conn.execute("select count(*) from sources").fetchone()[0] == 1
def test_contradiction_is_retained(tmp_path):
    c,s=controller(tmp_path); c.plan_universe("r",[{"date":"2025-01-01"}]); c.extract_and_link("r",source(),"support"); c.extract_and_link("r",source("official-2"),"refute"); assert "2025-01-01:resulting_range" in s.load("r")["state"]["contradicted_claims"]
def test_exhausted_evidence_is_insufficient(tmp_path):
    c,s=controller(tmp_path); c.plan_universe("r",[{"date":"2025-01-01"}]); assert c.complete("r",exhausted=True) == TerminalOutcome.INSUFFICIENT_EVIDENCE
def test_same_strategy_retry_maximum_one(tmp_path):
    c,s=controller(tmp_path); c.record_failure("r","A04","x","BAD"); c.record_failure("r","A04","x","BAD"); assert not c.can_retry("r","BAD","L1")
def test_calendar_planner_discovers_only_paired_official_routes():
    html='''<a href="/newsevents/pressreleases/monetary20250129a.htm">HTML</a><a href="/newsevents/pressreleases/monetary20250129a1.htm">Implementation Note</a><a href="/newsevents/pressreleases/monetary20250319a.htm">HTML</a>'''
    routes=discover_2025_routes(html); assert [(x.date,x.statement_url.endswith("a.htm")) for x in routes] == [("2025-01-29",True)]
def test_bounded_parser_does_not_guess_missing_range():
    facts=extract_bounded_facts("The Committee decided to maintain the target range for the federal funds rate at 4 to 4-1/4 percent.","2025-01-29")
    assert {x["field"] for x in facts} == {"direction","resulting_range"}
def test_unknown_action_and_unjustified_n1_fail_closed(tmp_path):
    c,_=controller(tmp_path)
    with pytest.raises(ValueError): c.dispatch("r","X9")
    with pytest.raises(ValueError): c.dispatch("r","N1")
def test_n1_context_retains_both_sides(tmp_path):
    c,s=controller(tmp_path); c.plan_universe("r",[{"date":"2025-01-01"}]); c.extract_and_link("r",source(),"support"); c.extract_and_link("r",source("other"),"refute")
    assert len(c.n1_context("r","2025-01-01:resulting_range")["evidence"]) == 2
def test_progress_ignores_irrelevant_source(tmp_path):
    c,s=controller(tmp_path); c.plan_universe("r",[{"date":"2025-01-01"}]); before=s.load("r")["state"]["progress_metrics"]; c.ingest("r",source("irrelevant","unrelated text")); after=s.load("r")["state"]["progress_metrics"]
    assert before == after
def test_evidence_contains_metric_and_derivative_family(tmp_path):
    c,s=controller(tmp_path); c.plan_universe("r",[{"date":"2025-01-01"}]); c.extract_and_link("r",source()); link=s.load("r")["state"]["claim_evidence_map"]["2025-01-01:resulting_range"][0]
    assert link["quality"]["authority"] == 1.0 and link["quality"]["independence_family"] == "official-1"
def test_recovery_selects_smallest_incomplete_claim(tmp_path):
    c,s=controller(tmp_path); c.plan_universe("r",[{"date":"2025-02-01"},{"date":"2025-01-01"}]); assert c.recover("r") == "2025-01-01:direction"
def test_independent_verifier_blocks_unverified_supported_claims(tmp_path):
    c,s=controller(tmp_path); c.plan_universe("r",[{"date":"2025-01-01"}]);
    for field in ("direction","resulting_range"):
        text="The direction is unchanged. The range is 4.00 to 4.25."
        c.link_extraction("r",source(field,text),{"meeting_date":"2025-01-01","field":field,"value":"x","statement_span":"direction is unchanged" if field=="direction" else "range is 4.00 to 4.25"})
    assert c.complete("r",exhausted=True) == TerminalOutcome.INSUFFICIENT_EVIDENCE
def test_checkpoint_rolls_back_on_failure(tmp_path):
    c,s=controller(tmp_path)
    with pytest.raises(RuntimeError):
        with s.checkpoint("r","RESEARCHING") as state:
            state["required_claims"].append({"id":"bad"}); raise RuntimeError("interrupt")
    assert not s.load("r")["state"]["required_claims"]
def test_status_survives_store_restart(tmp_path):
    c,s=controller(tmp_path); c.plan_universe("r",[{"date":"2025-01-01"}]); path=s.conn.execute("PRAGMA database_list").fetchone()[2]; s.close()
    restarted=RunStore(path); restored=ResearchController(restarted,load_eir(FIXTURE)); assert restored.status("r")["required_claims"] == 2; restarted.close()
def test_live_adapter_is_opt_in():
    from eir_runtime.adapters import OfficialWebRetrieval
    with pytest.raises(PermissionError): OfficialWebRetrieval().retrieve("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
def test_stagnation_forces_material_l3_replan(tmp_path):
    c,s=controller(tmp_path); c.record_failure("r","A04","x","BAD"); c.record_failure("r","A04","x","BAD")
    assert c.replan("r","BAD","L1") == "L3"
    with pytest.raises(ValueError): c.replan("r","BAD","L3")
    assert c.replan("r","BAD","L3",material_change=True) == "L3"
def test_schema_pressure_is_recorded_not_promoted(tmp_path):
    c,s=controller(tmp_path); c.record_schema_pressure("r","citation","needs richer span")
    assert s.load("r")["state"]["schema_pressure_log"][0]["candidate_concept"] == "citation"
def test_validated_source_has_immutable_artifact_and_registry(tmp_path):
    c,s=controller(tmp_path); c.ingest("r",source()); row=s.conn.execute("select hash from sources").fetchone()
    assert s.has_artifact(row[0]) and s.load("r")["state"]["source_registry"]["official-1"]["content_hash"] == row[0]
def test_retrieval_failure_is_uncertainty_and_fingerprint(tmp_path):
    c,s=controller(tmp_path); c.retrieval=FakeRetrieval({}); assert c.retrieve("r","missing") is None
    state=s.load("r")["state"]; assert state["uncertainties"][0]["class"] == "temporary_retrieval_unavailability" and state["failure_fingerprints"]
def test_recovery_reconciles_inflight_without_reissue(tmp_path):
    c,s=controller(tmp_path); s.action("r","RETRIEVE:x","INFLIGHT",{"route":"x"}); c.plan_universe("r",[{"date":"2025-01-01"}]); assert c.recover("r") == "2025-01-01:direction"
    assert s.conn.execute("select status from actions where action_id='RETRIEVE:x'").fetchone()[0] == "RECONCILED"
def test_route_manifest_survives_restart_and_cannot_change(tmp_path):
    c,s=controller(tmp_path); c.plan_universe("r",[{"date":"2025-01-01"}]); routes=[{"date":"2025-01-01","statement_url":"https://x/a","implementation_url":"https://x/b"}]; c.save_routes("r",routes)
    assert s.load("r")["state"]["route_manifest"] == routes
    with pytest.raises(ValueError): c.save_routes("r",[{"date":"2025-01-01","statement_url":"https://x/changed","implementation_url":"https://x/b"}])
