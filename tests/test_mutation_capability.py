import json
import os
import subprocess

import pytest

from eir_runtime.mutation_capability import MutmutCapability


def test_mutmut_capability_normalizes_structured_report_without_parsing_console_text(tmp_path):
    report = tmp_path / "mutmut-result.json"
    report.write_text(json.dumps({"killed": 3, "survived": 2, "timeout": 1, "survivors": [{"mutant_id": "M-2", "target": "app/user.py"}]}), encoding="utf-8")
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "All good (not parsed)", "")

    capability = MutmutCapability(runner=runner, which=lambda _: "mutmut")
    result, evidence = capability.execute("app/user.py", cwd=tmp_path, timeout_seconds=12, result_path=report)
    assert calls[0][0] == ["mutmut", "run", "--paths-to-mutate", "app/user.py"]
    assert result.mutation_score == 50.0
    assert result.surviving_mutants[0]["id"] == "M-2"
    assert evidence.exit_code == 0 and not evidence.timed_out


def test_mutmut_capability_treats_missing_tool_failed_process_and_missing_report_as_invalid(tmp_path):
    missing = MutmutCapability(which=lambda _: None)
    result, evidence = missing.execute("app/user.py", cwd=tmp_path, timeout_seconds=1, result_path=tmp_path / "none.json")
    assert result.invalid and evidence.exit_code is None

    failed = MutmutCapability(
        which=lambda _: "mutmut",
        runner=lambda command, **kwargs: subprocess.CompletedProcess(command, 2, "", "tool failure"),
    )
    result, evidence = failed.execute("app/user.py", cwd=tmp_path, timeout_seconds=1, result_path=tmp_path / "none.json")
    assert result.invalid and evidence.exit_code == 2


def test_mutmut_capability_rejects_unstructured_or_inconsistent_reports(tmp_path):
    report = tmp_path / "bad.json"
    report.write_text(json.dumps({"killed": 1, "survived": 0, "timeout": 0, "survivors": [{"id": "extra"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="exceed"):
        MutmutCapability.parse_result(report)


@pytest.mark.mutation_integration
@pytest.mark.skipif(os.environ.get("EIR_RUN_MUTMUT") != "1", reason="set EIR_RUN_MUTMUT=1 with an installed mutmut reporter contract")
def test_real_mutmut_tool_contract_requires_real_structured_artifact():
    target, cwd, report = (os.environ[name] for name in ("EIR_MUTMUT_TARGET", "EIR_MUTMUT_CWD", "EIR_MUTMUT_RESULT"))
    result, evidence = MutmutCapability().execute(target, cwd=cwd, timeout_seconds=300, result_path=report)
    assert evidence.exit_code == 0 and not evidence.timed_out
    assert not result.invalid and result.mutation_score is not None
