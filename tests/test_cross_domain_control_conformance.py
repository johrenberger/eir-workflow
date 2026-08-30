"""Behavioral control-plane contract run against every registered adapter."""
import json
from pathlib import Path

import pytest

from eir_runtime import ActionKey, RunController, RunStore
from eir_runtime.registry import create_adapter
from eir_runtime.validation import load_eir


ROOT = Path(__file__).parents[1]


def contract(domain):
    if domain == "technical-research":
        return load_eir(ROOT / "fixtures" / "domain3.yaml")
    return json.loads((ROOT / "fixtures" / "test-automation-e2.json").read_text())


@pytest.mark.parametrize("domain", ["technical-research", "test-automation"])
def test_registered_domains_share_validation_retry_l3_h1_and_terminal_protection(tmp_path, domain):
    store = RunStore(tmp_path / f"{domain}.sqlite")
    controller = RunController(store, create_adapter(domain)); controller.start("run", contract(domain))
    key = ActionKey("CANDIDATE", "opaque-unit", "L1", "same-input")
    for _ in range(2):
        controller.lifecycle.record_failure("run", key, signature="NO_PROGRESS", phase="EXECUTING")
    assert controller.control_route("run", key, signature="NO_PROGRESS", max_attempts_per_strategy=2, max_total_attempts=8, max_l4_attempts=2) == "L3"
    l3 = ActionKey("CANDIDATE", "opaque-unit", "L3", "changed-input")
    with pytest.raises(ValueError, match="material"):
        controller.control_route("run", l3, signature="NO_PROGRESS", max_attempts_per_strategy=2, max_total_attempts=8, max_l4_attempts=2)
    handoff = controller.handoff("run", l3, reason="bounded uncertainty", evidence={"fingerprint": "NO_PROGRESS"})
    assert controller.handoff("run", l3, reason="ignored", evidence={}) == handoff
    controller.complete("run", exhausted=True)
    assert store.load("run")["phase"] == "TERMINAL"
    with pytest.raises(ValueError, match="terminal"):
        controller.start("run", contract(domain))
    store.close()
