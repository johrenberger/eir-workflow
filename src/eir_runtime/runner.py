"""Resumable execution of a previously checkpointed route manifest."""
from __future__ import annotations
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
import re
from .planner import extract_bounded_facts

class RoutePolicy:
    """Deterministic, injectable L3 route substitution policy."""
    def changed_route(self, route: str, claim_ids: list[str]) -> str | None: raise NotImplementedError

class OfficialFomcRoutePolicy(RoutePolicy):
    """L3 fallback from an official statement to its same-date implementation note."""
    def changed_route(self, route: str, claim_ids: list[str]) -> str | None:
        parts = urlsplit(route)
        if parts.scheme != "https" or not parts.netloc.endswith("federalreserve.gov"): return None
        match = re.fullmatch(r"/newsevents/pressreleases/monetary(\d{8})a\.htm", parts.path, re.I)
        if match:
            path = f"/newsevents/pressreleases/monetary{match.group(1)}a1.htm"
            return urlunsplit((parts.scheme, parts.netloc, path, "", ""))
        match = re.fullmatch(r"/newsevents/pressreleases/monetary(\d{8})a1\.htm", parts.path, re.I)
        if not match: return None
        path = f"/monetarypolicy/fomcminutes{match.group(1)}.htm"
        return urlunsplit((parts.scheme, parts.netloc, path, "", ""))

def retrieve_with_control(controller, run_id: str, route: str, claim_ids: list[str], retrieve, *, route_policy: RoutePolicy | None=None, retry_hook: Callable[[int], None] | None=None):
    strategy, attempts, active_route = "L1", 0, route
    while True:
        try: return retrieve(active_route)
        except Exception as exc:
            attempts += 1; signature = type(exc).__name__; decisions = []
            for claim_id in claim_ids:
                controller.record_failure(run_id, "A03", active_route, signature, strategy, claim_id)
                decisions.append(controller.control_route(run_id, claim_id, signature, strategy, material_change=(strategy == "L3")))
            decision = decisions[0]
            if decision.startswith("RETRY_"):
                if retry_hook: retry_hook(attempts)
                continue
            if decision == "L3":
                changed = route_policy.changed_route(active_route, claim_ids) if route_policy else None
                if not changed or changed == active_route:
                    return None
                active_route, strategy = changed, "L3"
                continue
            if decision == "H1":
                for claim_id in claim_ids:
                    try: controller.escalate_h1(run_id, claim_id, exhausted=True)
                    except ValueError: pass
            return None

def run_routes(controller, run_id: str, routes: list, retrieve, *, before_meeting: Callable[[str], None] | None = None, route_policy: RoutePolicy | None=None, retry_hook: Callable[[int], None] | None=None) -> None:
    for meeting in routes:
        state = controller.store.load(run_id)["state"]
        statuses = {claim["id"]: claim["status"] for claim in state["required_claims"]}
        if all(statuses.get(f"{meeting.date}:{field}") == "supported" for field in ("direction", "resulting_range")):
            continue
        if before_meeting: before_meeting(meeting.date)
        claim_ids=[f"{meeting.date}:direction", f"{meeting.date}:resulting_range"]
        statement = retrieve_with_control(controller, run_id, meeting.statement_url, claim_ids, retrieve, route_policy=route_policy, retry_hook=retry_hook)
        implementation = retrieve_with_control(controller, run_id, meeting.implementation_url, claim_ids, retrieve, route_policy=route_policy, retry_hook=retry_hook)
        if not statement or not implementation: continue
        for source in (statement, implementation):
            for extracted in extract_bounded_facts(source.content, meeting.date): controller.link_extraction(run_id, source, extracted)
        for field in ("direction", "resulting_range"):
            controller.independently_verify(run_id, f"{meeting.date}:{field}", implementation)
