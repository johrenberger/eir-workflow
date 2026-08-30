from eir_runtime.test_generation import build_context, proposal_fingerprint, validate_proposal


MANIFEST = {"allowed_change_paths": ["tests/test_user.py"]}
GAP = {"id": "branch:app/user.py:12->13", "status": "unresolved"}


def proposal(**overrides):
    value = {"gap_id": GAP["id"], "files": ["tests/test_user.py"], "intent": "exercise branch", "patch": "assert branch", "assumptions": [], "expected_evidence": {"branch": [12, 13]}}
    value.update(overrides); return value


def test_n1_proposal_is_bounded_to_one_unresolved_gap_and_allowed_test_paths():
    assert validate_proposal(proposal(), MANIFEST, [GAP]) == []
    assert "disallowed_change_path" in validate_proposal(proposal(files=["app/user.py"]), MANIFEST, [GAP])
    assert "proposal_cannot_declare_success" in validate_proposal(proposal(success=True), MANIFEST, [GAP])


def test_generation_context_and_fingerprint_are_deterministic_and_l3_can_change_context():
    first = build_context(GAP, target_source="source", relevant_tests={"tests/test_user.py": "test"})
    repeated = build_context(GAP, target_source="source", relevant_tests={"tests/test_user.py": "test"})
    changed = build_context(GAP, target_source="source", relevant_tests={"tests/test_user.py": "test", "tests/test_api.py": "api"}, strategy="L3")
    assert first["context_hash"] == repeated["context_hash"] and first["context_hash"] != changed["context_hash"]
    assert proposal_fingerprint(proposal(), validation_category="no_progress", strategy="L1") == proposal_fingerprint(proposal(), validation_category="no_progress", strategy="L1")
