"""Opt-in E2 contract against the real FastAPI target; no target files are written."""
import json
import os
import subprocess
import hashlib
from pathlib import Path

import pytest

from eir_runtime import ActionKey, RunController, RunStore, TerminalOutcome
from eir_runtime.registry import create_adapter


TARGET = Path(os.environ.get("EIR_E2_TARGET", ""))
PYTHON = os.environ.get("EIR_E2_PYTHON")
ROOT = Path(__file__).parents[1]
BASELINE_STATUS = {
    " D tests/api/conftest.py", " D tests/api/test_users.py", " D tests/contract/test_contract.py",
    " D tests/performance/README.md", " D tests/performance/k6_baseline.js",
    " D tests/performance/k6_soak.js", " D tests/performance/k6_spike.js",
    " D tests/performance/test_baseline_smoke.py",
}


@pytest.mark.skipif(not TARGET.exists() or not PYTHON or not Path(PYTHON).exists(), reason="set EIR_E2_TARGET and EIR_E2_PYTHON for the real-target E2 contract")
def test_e2_real_target_replays_through_shared_controller(tmp_path):
    manifest = json.loads((ROOT / "fixtures" / "test-automation-e2.json").read_text())
    env = os.environ.copy(); env["PYTHONPATH"] = str(TARGET); env["PYTHONUNBUFFERED"] = "1"
    data = tmp_path / ".coverage.e2"
    production = TARGET / "app" / "user.py"
    production_hash_before = hashlib.sha256(production.read_bytes()).hexdigest()
    run = subprocess.run([PYTHON, "-m", "coverage", "run", f"--data-file={data}", "--source=app", "--branch", "-m", "pytest", str(TARGET / "tests"), "-q", "--rootdir", str(tmp_path)], cwd=tmp_path, env=env, text=True, capture_output=True, timeout=60)
    report = tmp_path / "coverage.json"
    generated = subprocess.run([PYTHON, "-m", "coverage", "json", f"--data-file={data}", "-o", str(report)], cwd=tmp_path, text=True, capture_output=True, timeout=60)
    validation = {"watchdog": {"returncode": run.returncode, "timed_out": False}, "stdout": run.stdout, "production_unchanged": production_hash_before == hashlib.sha256(production.read_bytes()).hexdigest()}
    coverage = json.loads(report.read_text())
    status = set(subprocess.run(["git", "-c", "safe.directory=F:/coding/pytest-fastapi-crud-example", "-C", str(TARGET), "status", "--porcelain"], text=True, capture_output=True, check=True).stdout.splitlines())
    changed_paths = [entry[3:] for entry in sorted(status - BASELINE_STATUS)]
    adapter = create_adapter("test-automation")
    store = RunStore(tmp_path / "eir.sqlite"); controller = RunController(store, adapter)
    try:
        controller.start("e2", manifest)
        change_set = adapter.validate_change_set(manifest, changed_paths)
        measurement = adapter.measurement_from_evidence(manifest, validation, coverage)
        assert generated.returncode == 0 and change_set["valid"]
        progress = controller.record_measurement("e2", ActionKey("TEST_EVIDENCE", manifest["target_module"], "L1", measurement["evidence_artifact_hashes"]["coverage"]), measurement)
        assert progress["improved"] and controller.complete("e2", exhausted=True) == TerminalOutcome.SUPPORTED
    finally:
        store.close()
