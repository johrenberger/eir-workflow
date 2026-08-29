import os
import pytest
from eir_runtime.adapters import OfficialWebRetrieval
from eir_runtime.planner import CALENDAR_URL, discover_2025_routes
from eir_runtime.runner import OfficialFomcRoutePolicy

pytestmark = pytest.mark.live
@pytest.mark.skipif(os.getenv("EIR_RUN_LIVE") != "1", reason="set EIR_RUN_LIVE=1 for official-network contract tests")
def test_official_calendar_discovery_and_l3_policy_contract():
    calendar=OfficialWebRetrieval(allow_network=True).retrieve(CALENDAR_URL)
    routes=discover_2025_routes(calendar.content)
    assert len(routes) == 8
    policy=OfficialFomcRoutePolicy()
    assert all(policy.changed_route(route.statement_url, []) == route.implementation_url for route in routes)
