"""Bounded N1 test proposal validation; deterministic tools still decide quality."""
from __future__ import annotations

import hashlib
import json


def validate_proposal(proposal: dict, manifest: dict, gaps: list[dict]) -> list[str]:
    required = {"gap_id", "files", "intent", "patch", "assumptions", "expected_evidence"}
    errors = [f"missing:{field}" for field in sorted(required - set(proposal))]
    unresolved = {gap["id"] for gap in gaps if gap.get("status") == "unresolved"}
    if proposal.get("gap_id") not in unresolved: errors.append("unknown_or_resolved_gap")
    allowed = {path.replace("\\", "/") for path in manifest["allowed_change_paths"]}
    files = {path.replace("\\", "/") for path in proposal.get("files", [])}
    if not files or not files <= allowed: errors.append("disallowed_change_path")
    if proposal.get("success") is True: errors.append("proposal_cannot_declare_success")
    return errors


def build_context(gap: dict, *, target_source: str, relevant_tests: dict[str, str], previous_fingerprint: str | None = None, strategy: str = "L1") -> dict:
    """Deterministically bound N1 context to the selected gap and related files."""
    context = {"gap": gap, "target_source": target_source, "tests": dict(sorted(relevant_tests.items())), "previous_fingerprint": previous_fingerprint, "strategy": strategy}
    encoded = json.dumps(context, sort_keys=True, separators=(",", ":")).encode()
    return {**context, "context_hash": hashlib.sha256(encoded).hexdigest()}


def proposal_fingerprint(proposal: dict, *, validation_category: str, strategy: str) -> str:
    value = {"gap_id": proposal.get("gap_id"), "files": sorted(proposal.get("files", [])), "patch": proposal.get("patch"), "validation_category": validation_category, "strategy": strategy}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
