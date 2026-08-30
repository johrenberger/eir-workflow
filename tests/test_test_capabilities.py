import pytest

from eir_runtime.test_capabilities import CoverageCapability, TestExecutionResult


def execution(**overrides):
    value = {"collected": 3, "passed": 3, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0, "timed_out": False, "duration_seconds": 0.1}
    value.update(overrides)
    return value


def test_structured_execution_success_is_valid_without_stdout_parsing():
    assert TestExecutionResult.from_structured(execution()).full_suite_passed


@pytest.mark.parametrize("override", [{"exit_code": None, "timed_out": True}, {"failed": 1, "passed": 2}, {"collection_errors": 1}])
def test_structured_execution_failure_timeout_or_collection_error_is_not_success(override):
    assert not TestExecutionResult.from_structured(execution(**override)).full_suite_passed


def test_coverage_capability_normalizes_lines_branches_and_missing_details():
    raw = {"meta": {"version": "7"}, "totals": {"percent_covered": 90.0, "percent_branches_covered": 80.0}, "files": {r"C:\repo\app\user.py": {"summary": {"percent_covered": 91.0, "percent_branches_covered": 75.0}, "missing_lines": [10], "missing_branches": [[11, 12]]}}}
    result = CoverageCapability().normalize(raw, "app/user.py")
    assert result.valid and result.target.line_coverage == 91.0 and result.target.branch_coverage == 75.0
    assert result.target.missing_lines == (10,) and result.target.missing_branches == ((11, 12),)


def test_coverage_capability_marks_absent_target_invalid():
    raw = {"meta": {"version": "7"}, "totals": {"percent_covered": 90.0}, "files": {}}
    assert not CoverageCapability().normalize(raw, "app/user.py").valid
