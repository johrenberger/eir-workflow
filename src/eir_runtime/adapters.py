from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class RetrievedSource:
    uri: str
    canonical_id: str
    content: str
    publisher: str
    source_class: str
    provenance_family: str
    available: bool = True


class RetrievalAdapter(Protocol):
    def retrieve(self, route: str) -> RetrievedSource: ...


class ExtractionAdapter(Protocol):
    def extract(self, source: RetrievedSource) -> dict: ...

class InterpretationAdapter(Protocol):
    def interpret(self, context: dict) -> dict: ...


class FakeRetrieval:
    """Scripted fixture adapter; intentionally has no network code."""
    def __init__(self, scripted: dict[str, RetrievedSource]): self.scripted = scripted
    def retrieve(self, route: str) -> RetrievedSource:
        if route not in self.scripted: raise LookupError(f"unavailable route: {route}")
        return self.scripted[route]


class FakeExtractor:
    def __init__(self, payload: dict | str): self.payload = payload; self.calls = 0
    def extract(self, source: RetrievedSource) -> dict:
        self.calls += 1
        if not isinstance(self.payload, dict): raise ValueError("non-schema extraction")
        return self.payload

class FakeInterpreter:
    def __init__(self, payload: dict): self.payload=payload; self.calls=0
    def interpret(self, context: dict) -> dict:
        self.calls += 1; return self.payload


class OfficialWebRetrieval:
    """Explicit opt-in HTTP reader for official Federal Reserve routes.

    It intentionally accepts a concrete URL rather than doing autonomous search;
    source selection remains a durable D1 controller decision.
    """
    def __init__(self, *, allow_network: bool = False): self.allow_network = allow_network
    def retrieve(self, route: str) -> RetrievedSource:
        if not self.allow_network: raise PermissionError("live retrieval is opt-in")
        parts = urlsplit(route)
        if parts.scheme != "https" or not parts.netloc.endswith("federalreserve.gov"):
            raise ValueError("only HTTPS federalreserve.gov routes are permitted")
        canonical = urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))
        with urlopen(Request(route, headers={"User-Agent": "eir-runtime/0.1"}), timeout=20) as response:
            content=response.read().decode("utf-8", errors="replace")
        source_class="official_fomc_statement" if "/monetarypolicy/fomc" in parts.path else "official_federal_reserve_calendar_or_archive"
        return RetrievedSource(route, canonical, content, "Federal Reserve", source_class, canonical)
