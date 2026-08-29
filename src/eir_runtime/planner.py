"""Deterministic route discovery from the official FOMC calendar."""
from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re

BASE = "https://www.federalreserve.gov"
CALENDAR_URL = BASE + "/monetarypolicy/fomccalendars.htm"

@dataclass(frozen=True)
class MeetingRoute:
    date: str
    statement_url: str
    implementation_url: str
    calendar_url: str = CALENDAR_URL

def discover_2025_routes(calendar_html: str) -> list[MeetingRoute]:
    """Discover—not encode—the 2025 decision dates and official artifact routes.

    The selector is deliberately narrow: calendar links labeled as the official
    statement and implementation note route families. A changed Fed page shape
    produces an empty/partial universe, which completion treats as insufficient.
    """
    found: dict[str, dict[str, str]] = {}
    for href in re.findall(r'href=["\']([^"\']+)["\']', unescape(calendar_html), flags=re.I):
        match = re.search(r"monetary(2025\d{4})a(1)?\.htm$", href, flags=re.I)
        if not match: continue
        date = f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}"
        found.setdefault(date, {})["implementation" if match.group(2) else "statement"] = BASE + href
    return [MeetingRoute(date, routes["statement"], routes["implementation"]) for date, routes in sorted(found.items()) if {"statement", "implementation"} <= set(routes)]

def extract_bounded_facts(document: str, meeting_date: str) -> list[dict]:
    """Conservative deterministic parser; absence is an uncertainty, never a guess."""
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(document))).strip()
    direction = re.search(r"decided to (raise|lower|maintain) the target range[^.]*\.", plain, re.I)
    range_ = re.search(r"target range[^.]{0,180}?(?:at|to)\s+([0-9¼½¾/ .\-‑–]+?\s+to\s+[0-9¼½¾/ .\-‑–]+?\s+percent)[^.]*\.", plain, re.I)
    facts: list[dict] = []
    if direction:
        facts.append({"meeting_date": meeting_date, "field": "direction", "value": {"raise":"increase", "lower":"decrease", "maintain":"unchanged"}[direction.group(1).lower()], "statement_span": direction.group(0)})
    if range_:
        facts.append({"meeting_date": meeting_date, "field": "resulting_range", "value": range_.group(1).strip(), "statement_span": range_.group(0)})
    return facts
