from eir_runtime.test_quality import MutationResult, QualityEvaluator, derive_gaps, select_gap


def measure(**overrides):
    value = {"target_line_coverage": 80.0, "target_branch_coverage": 70.0, "full_suite_passed": True, "process_exit_code": 0, "watchdog_inactive": True, "production_unchanged": True, "valid_coverage": True, "unresolved_behavior_gaps": 0, "regressions": 0, "policy_violations": 0}
    value.update(overrides)
    return value


def test_quality_progress_accepts_branch_or_mutation_improvement_without_line_gain():
    evaluator = QualityEvaluator(); manifest = {"minimum_line_coverage": 90, "minimum_branch_coverage": 80, "minimum_mutation_score": 75}
    assert evaluator.progress(measure(mutation_score=60, surviving_mutants=4), measure(mutation_score=70, surviving_mutants=3), manifest)["improved"]
    assert evaluator.progress(measure(mutation_score=60, surviving_mutants=4), measure(target_branch_coverage=80, mutation_score=60, surviving_mutants=4), manifest)["reason"] == "branch_coverage"


def test_required_metric_regression_rejects_line_coverage_improvement():
    evaluator = QualityEvaluator(); manifest = {"minimum_line_coverage": 90, "minimum_mutation_score": 75}
    result = evaluator.progress(measure(target_line_coverage=80, mutation_score=90), measure(target_line_coverage=90, mutation_score=60), manifest)
    assert result["improved"] is False and result["reason"] == "required_metric_regression"


def test_mutation_and_coverage_gaps_are_durable_domain_records_with_deterministic_priority():
    mutation = MutationResult(4, 2, 2, 0, False, ({"id": "m1", "target": "app/user.py"},))
    gaps = derive_gaps({"target_module": "app/user.py", "missing_lines": [10], "missing_branches": [[12, 13]]}, mutation)
    assert select_gap(gaps)["type"] == "uncovered_branch"
    assert any(gap["type"] == "surviving_mutant" for gap in gaps)


def test_invalid_mutation_has_no_score():
    assert MutationResult(0, 0, 0, 0, True).mutation_score is None


def test_configured_metric_without_deterministic_evidence_is_invalid_progress_and_incomplete():
    evaluator = QualityEvaluator(); manifest = {"minimum_line_coverage": 90, "minimum_mutation_score": 75}
    after = measure(target_line_coverage=95)
    assert evaluator.progress(None, after, manifest) == {"improved": False, "reason": "invalid_measurement"}
    assert not evaluator.complete(after, manifest)
