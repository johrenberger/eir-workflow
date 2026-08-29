import argparse, hashlib, json, uuid
from pathlib import Path
from .adapters import OfficialWebRetrieval
from .engine import ResearchController
from .planner import CALENDAR_URL, discover_2025_routes, extract_bounded_facts
from .store import RunStore
from .runner import OfficialFomcRoutePolicy, run_routes
from .report import audit_bundle
from .validation import load_eir, validate_eir
from .core import ActionKey, RunController
from .registry import available_adapters, create_adapter
from .provenance import verify_e1c_to_e2
def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True); v=sub.add_parser("validate"); v.add_argument("eir")
    status=sub.add_parser("status", help="emit versioned machine-readable run status"); status.add_argument("eir"); status.add_argument("--db", required=True); status.add_argument("--run-id", required=True)
    audit=sub.add_parser("audit", help="write a claim-by-claim JSON audit bundle"); audit.add_argument("eir"); audit.add_argument("--db", required=True); audit.add_argument("--run-id", required=True); audit.add_argument("--out", required=True)
    live=sub.add_parser("live", help="opt-in official Federal Reserve evidence collection")
    live.add_argument("eir"); live.add_argument("--db", required=True); live.add_argument("--run-id", default=None); live.add_argument("--calendar-url", default=CALENDAR_URL)
    adapters=sub.add_parser("adapters", help="list registered objective adapters")
    test_evidence=sub.add_parser("test-evidence", help="ingest deterministic test validation and coverage evidence")
    test_evidence.add_argument("--adapter", choices=available_adapters(), default="test-automation")
    test_evidence.add_argument("--manifest", required=True); test_evidence.add_argument("--validation", required=True); test_evidence.add_argument("--coverage", required=True)
    test_evidence.add_argument("--db", required=True); test_evidence.add_argument("--run-id", required=True); test_evidence.add_argument("--changed-path", action="append", default=[])
    lineage=sub.add_parser("verify-lineage", help="verify E1C to E2 artifact lineage")
    lineage.add_argument("--e1c-baseline", required=True); lineage.add_argument("--e1c-coverage", required=True); lineage.add_argument("--e2-validation", required=True); lineage.add_argument("--e2-coverage", required=True)
    args=p.parse_args()
    if args.cmd == "validate":
        issues=validate_eir(load_eir(args.eir)); print(json.dumps([x.__dict__ for x in issues],indent=2)); raise SystemExit(bool(issues))
    if args.cmd == "adapters":
        print(json.dumps(list(available_adapters()), indent=2)); return
    if args.cmd == "verify-lineage":
        result=verify_e1c_to_e2(args.e1c_baseline,args.e1c_coverage,args.e2_validation,args.e2_coverage); print(json.dumps(result,indent=2)); raise SystemExit(not result["valid"])
    if args.cmd == "test-evidence":
        manifest=json.loads(Path(args.manifest).read_text(encoding="utf-8")); validation=json.loads(Path(args.validation).read_text(encoding="utf-8")); coverage=json.loads(Path(args.coverage).read_text(encoding="utf-8"))
        adapter=create_adapter(args.adapter)
        if not hasattr(adapter,"measurement_from_evidence"):
            raise ValueError(f"adapter {args.adapter} does not support test evidence ingestion")
        store=RunStore(args.db); controller=RunController(store,adapter)
        try:
            controller.start(args.run_id,manifest)
            change_set=adapter.validate_change_set(manifest,args.changed_path)
            measurement=adapter.measurement_from_evidence(manifest,validation,coverage)
            if not change_set["valid"]: measurement["production_unchanged"]=False
            for label, payload in (("validation",validation),("coverage",coverage)):
                content=json.dumps(payload,sort_keys=True,separators=(",",":")); store.artifact(hashlib.sha256(content.encode()).hexdigest(),content)
            key=ActionKey("TEST_EVIDENCE",manifest["target_module"],"L1",measurement["evidence_artifact_hashes"]["coverage"])
            decision=controller.record_measurement(args.run_id,key,measurement)
            if not change_set["valid"]:
                controller.lifecycle.record_failure(args.run_id,key,signature="DISALLOWED_CHANGE_SET",phase="RESEARCHING",payload={"change_set":change_set})
            outcome=controller.complete(args.run_id,exhausted=True)
            print(json.dumps({"outcome":outcome,"progress":decision,"change_set":change_set,"measurement":measurement,"objective_records":store.objective_records(args.run_id)},indent=2))
        finally: store.close()
        return
    if args.cmd in {"status", "audit"}:
        store=RunStore(args.db); controller=ResearchController(store,load_eir(args.eir))
        try:
            bundle=audit_bundle(store,controller,args.run_id)
            if args.cmd == "status": print(json.dumps(bundle["status"],indent=2))
            else:
                Path(args.out).parent.mkdir(parents=True,exist_ok=True); Path(args.out).write_text(json.dumps(bundle,indent=2),encoding="utf-8"); print(args.out)
        finally: store.close()
        return
    if args.cmd == "live":
        eir=load_eir(args.eir); store=RunStore(args.db); web=OfficialWebRetrieval(allow_network=True); controller=ResearchController(store,eir); run_id=args.run_id or str(uuid.uuid4())
        try:
            try: prior=store.load(run_id)
            except KeyError: prior=None
            controller.start(run_id)
            if prior:
                routes=[type("Route", (), x) for x in prior["state"]["route_manifest"]]
                if not routes: raise ValueError("cannot resume: no durable route manifest")
            else:
                calendar=web.retrieve(args.calendar_url); routes=discover_2025_routes(calendar.content); controller.plan_universe(run_id,[{"date":x.date,"provenance":calendar.canonical_id} for x in routes]); controller.save_routes(run_id,[x.__dict__ for x in routes]); controller.ingest(run_id,calendar)
            run_routes(controller, run_id, routes, web.retrieve, route_policy=OfficialFomcRoutePolicy())
            print(json.dumps(controller.status(run_id),indent=2)); print(controller.complete(run_id,exhausted=True));
        finally: store.close()

if __name__ == "__main__":
    main()
