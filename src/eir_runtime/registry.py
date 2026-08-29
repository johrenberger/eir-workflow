"""Explicit adapter registry; generic core never switches on a domain name."""
from __future__ import annotations

from .research_adapter import ResearchObjectiveAdapter
from .test_automation_adapter import TestAutomationObjectiveAdapter


_ADAPTERS = {
    "technical-research": ResearchObjectiveAdapter,
    "test-automation": TestAutomationObjectiveAdapter,
}


def available_adapters() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))


def create_adapter(name: str):
    try:
        return _ADAPTERS[name]()
    except KeyError as exc:
        raise ValueError(f"unknown adapter: {name}; available: {', '.join(available_adapters())}") from exc
