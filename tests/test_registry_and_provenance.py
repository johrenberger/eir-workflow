import json

import pytest

from eir_runtime import available_adapters, create_adapter
from eir_runtime.provenance import verify_e1c_to_e2


def test_registry_selects_adapters_without_core_domain_conditionals():
    assert available_adapters() == ("technical-research", "test-automation")
    assert type(create_adapter("test-automation")).__name__ == "TestAutomationObjectiveAdapter"
    with pytest.raises(ValueError, match="unknown adapter"):
        create_adapter("unknown")


def test_provenance_verifier_requires_e1c_baseline_and_coverage_lineage(tmp_path):
    baseline = tmp_path / "Experiment-1-Pytest-FastAPI-CRUD-E1C-Authoritative-Baseline.json"
    baseline_coverage = tmp_path / "Experiment-1-Pytest-FastAPI-CRUD-E1C-Authoritative-Coverage.json"
    e2 = tmp_path / "Experiment-2-Pytest-FastAPI-CRUD-Full-Validation.json"
    e2_coverage = tmp_path / "Experiment-2-Pytest-FastAPI-CRUD-Full-Coverage.json"
    baseline.write_text(json.dumps({"watchdog": {"returncode": 0}}))
    baseline_coverage.write_text(json.dumps({"totals": {"percent_covered": 91.9}}))
    e2.write_text(json.dumps({"watchdog": {"returncode": 0}, "evidence_lineage": [baseline.name, baseline_coverage.name]}))
    e2_coverage.write_text(json.dumps({"totals": {"percent_covered": 95.2}}))
    assert verify_e1c_to_e2(baseline, baseline_coverage, e2, e2_coverage)["valid"]
    e2.write_text(json.dumps({"watchdog": {"returncode": 0}, "evidence_lineage": []}))
    assert verify_e1c_to_e2(baseline, baseline_coverage, e2, e2_coverage)["errors"] == ["e2_missing_e1c_lineage_reference"]
