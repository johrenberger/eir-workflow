from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any

TOP_LEVEL = ("metadata", "objective", "policy", "environment", "observations", "state", "actions", "evidence", "uncertainty", "control", "recovery", "human", "completion")

@dataclass(frozen=True)
class Diagnostic:
    rule: str; path: str; message: str

def load_eir(path: str | Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    try:
        value = json.loads(text)  # JSON is a strict YAML subset; default fixture is dependency-free.
    except json.JSONDecodeError:
        try:
            import yaml  # Optional support for ordinary YAML documents.
        except ModuleNotFoundError as exc:
            raise ValueError("Non-JSON YAML requires optional PyYAML: pip install PyYAML") from exc
        value = yaml.safe_load(text)
    if not isinstance(value, dict): raise ValueError("EIR YAML must be a mapping")
    return value

def validate_eir(eir: dict[str, Any]) -> list[Diagnostic]:
    errors: list[Diagnostic] = []
    def need(rule: int, path: str, condition: bool, message: str) -> None:
        if not condition: errors.append(Diagnostic(f"V{rule:03}", path, message))
    need(1, "$", set(eir) == set(TOP_LEVEL), "must contain all and only frozen top-level sections")
    metadata = eir.get("metadata", {}); need(2, "metadata", metadata.get("eir_version") == "1.0" and metadata.get("schema_freeze") is True, "requires frozen EIR v1.0 metadata")
    primary = eir.get("objective", {}).get("primary", {}); need(3, "objective.primary", bool(primary.get("description")) and "answer" not in str(primary).lower(), "objective must be explicit and non-answer-encoding")
    desired = eir.get("objective", {}).get("desired_state", {}); need(4, "objective.desired_state", {"required_claim_coverage", "material_unresolved_contradictions", "independent_verification_complete"} <= set(desired), "desired state must be measurable")
    need(5, "objective.constraints", bool(eir.get("objective", {}).get("constraints")), "constraints required")
    rules = eir.get("policy", {}).get("rules", []); need(6, "policy.rules", bool(rules) and all({"id", "condition", "target"} <= set(x) for x in rules), "enforceable policy rules required")
    env = eir.get("environment", {}); need(7, "environment", bool(env.get("authoritative_systems")) and bool(env.get("execution_limits")), "authorities and limits required")
    obs = eir.get("observations", {}); need(8, "observations", {"deterministic", "bounded_structured_extraction", "non_deterministic"} <= set(obs), "observation classes required")
    state = eir.get("state", {}).get("fields", {}); need(9, "state.fields", {"required_claims", "supported_claims", "unsupported_claims", "contradicted_claims", "claim_evidence_map"} <= set(state), "durable claim fields required")
    actions = eir.get("actions", []); need(10, "actions", bool(actions) and all({"id", "class", "output"} <= set(x) for x in actions), "bounded action contracts required")
    need(11, "evidence", bool(eir.get("evidence", {}).get("model")), "domain evidence metric required")
    minimum = eir.get("evidence", {}).get("model", {}).get("material_claim_minimum", [])
    minimum_text = " ".join(map(str, minimum)).lower()
    need(12, "evidence.model.material_claim_minimum", "direct" in minimum_text and "independent" in minimum_text, "traceable direct evidence and independent verification required")
    need(13, "uncertainty", bool(eir.get("uncertainty", {}).get("classes")), "explicit uncertainty required")
    need(14, "control.retry_policy", bool(eir.get("control", {}).get("retry_policy")), "retry policy required")
    levels = eir.get("control", {}).get("levels", {}); need(15, "control.levels", all(f"L{i}" in levels for i in range(6)) and levels.get("L3", {}).get("required_change") is True, "L0-L5 and material L3 change required")
    need(16, "recovery", bool(eir.get("recovery", {}).get("restart_protocol")), "restart protocol required")
    need(17, "human", bool(eir.get("human", {}).get("escalation_conditions")), "bounded human escalation required")
    outcomes = eir.get("completion", {}).get("terminal_outcomes", {}); need(18, "completion.terminal_outcomes", set(outcomes) == {"SUPPORTED", "INSUFFICIENT_EVIDENCE", "FAILED"}, "exact terminal outcomes required")
    supported_conditions = outcomes.get("SUPPORTED", {}).get("conditions", [])
    need(19, "completion.terminal_outcomes.SUPPORTED", "independent" in " ".join(map(str, supported_conditions)).lower(), "supported outcome requires independent verification")
    need(20, "policy.rules", any("schema" in str(x).lower() for x in rules), "schema pressure must be preserved")
    return errors
