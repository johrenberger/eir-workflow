from copy import deepcopy
from pathlib import Path
import pytest
from eir_runtime import load_eir, validate_eir

FIXTURE=Path(__file__).parents[1] / "fixtures" / "domain3.yaml"

def mutate(e, rule):
    if rule == 1: e["extra"]={}
    elif rule == 2: e["metadata"]["eir_version"]="2.0"
    elif rule == 3: e["objective"]["primary"]={}
    elif rule == 4: e["objective"]["desired_state"]={}
    elif rule == 5: e["objective"]["constraints"]=[]
    elif rule == 6: e["policy"]["rules"][0].pop("target")
    elif rule == 7: e["environment"]["authoritative_systems"]=[]
    elif rule == 8: e["observations"].pop("deterministic")
    elif rule == 9: e["state"]["fields"].pop("claim_evidence_map")
    elif rule == 10: e["actions"][0].pop("output")
    elif rule == 11: e["evidence"]={}
    elif rule == 12: e["evidence"]["model"]["material_claim_minimum"]=["corroboration only"]
    elif rule == 13: e["uncertainty"]["classes"]=[]
    elif rule == 14: e["control"].pop("retry_policy")
    elif rule == 15: e["control"]["levels"]["L3"]["required_change"]=False
    elif rule == 16: e["recovery"]["restart_protocol"]=[]
    elif rule == 17: e["human"]["escalation_conditions"]=[]
    elif rule == 18: e["completion"]["terminal_outcomes"].pop("FAILED")
    elif rule == 19: e["completion"]["terminal_outcomes"]["SUPPORTED"]["conditions"]=["coverage complete"]
    elif rule == 20: e["policy"]["rules"]=[e["policy"]["rules"][0]]
    return e

@pytest.mark.parametrize("rule",range(1,21))
def test_each_v_rule_has_a_negative_fixture(rule):
    e=mutate(deepcopy(load_eir(FIXTURE)),rule)
    assert f"V{rule:03}" in {x.rule for x in validate_eir(e)}

def test_canonical_fixture_round_trips_without_top_level_change(tmp_path):
    original=load_eir(FIXTURE); path=tmp_path/"roundtrip.yaml"; import yaml
    path.write_text(yaml.safe_dump(original),encoding="utf-8")
    assert set(load_eir(path)) == set(original)
