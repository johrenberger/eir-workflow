"""Structural conformance checks for ObjectiveAdapter implementations."""
from __future__ import annotations

import inspect


REQUIRED_METHODS = {
    "validate_contract": (),
    "compare": ("before", "after"),
    "recovery_unit": ("state", "records"),
    "completion": ("state", "records", "exhausted"),
}


def adapter_conformance_errors(adapter) -> list[str]:
    errors = []
    for method_name, parameters in REQUIRED_METHODS.items():
        method = getattr(adapter, method_name, None)
        if not callable(method):
            errors.append(f"missing:{method_name}")
            continue
        available = inspect.signature(method).parameters
        if method_name == "validate_contract" and not available:
            errors.append("signature:validate_contract:contract")
            continue
        missing = [parameter for parameter in parameters if parameter not in available]
        if missing:
            errors.append(f"signature:{method_name}:{','.join(missing)}")
    return errors
