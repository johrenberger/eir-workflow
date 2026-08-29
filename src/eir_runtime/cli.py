import argparse, json, uuid
from pathlib import Path
from .adapters import OfficialWebRetrieval
from .engine import ResearchController
from .planner import CALENDAR_URL, discover_2025_routes, extract_bounded_facts
from .store import RunStore
from .runner import OfficialFomcRoutePolicy, run_routes
from .report import audit_bundle
from .validation import load_eir, validate_eir
def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True); v=sub.add_parser("validate"); v.add_argument("eir")
    status=sub.add_parser("status", help="emit versioned machine-readable run status"); status.add_argument("eir"); status.add_argument("--db", required=True); status.add_argument("--run-id", required=True)
    audit=sub.add_parser("audit", help="write a claim-by-claim JSON audit bundle"); audit.add_argument("eir"); audit.add_argument("--db", required=True); audit.add_argument("--run-id", required=True); audit.add_argument("--out", required=True)
    live=sub.add_parser("live", help="opt-in official Federal Reserve evidence collection")
    live.add_argument("eir"); live.add_argument("--db", required=True); live.add_argument("--run-id", default=None); live.add_argument("--calendar-url", default=CALENDAR_URL)
    args=p.parse_args()
    if args.cmd == "validate":
        issues=validate_eir(load_eir(args.eir)); print(json.dumps([x.__dict__ for x in issues],indent=2)); raise SystemExit(bool(issues))
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
