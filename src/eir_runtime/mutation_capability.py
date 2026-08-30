"""Concrete, injectable mutation-tool boundary for Test Automation.

The generic EIR runtime never imports this module.  It runs ``mutmut`` and
accepts only a structured result artifact; console text is retained as
diagnostic evidence and is never converted into a quality score.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .test_quality import MutationResult


@dataclass(frozen=True)
class MutationCommandEvidence:
    command: tuple[str, ...]
    exit_code: int | None
    timed_out: bool
    stdout: str
    stderr: str


class MutmutCapability:
    """Run mutmut behind an injectable process boundary.

    ``result_path`` is an explicit integration contract: a caller-owned
    mutmut reporter/wrapper must emit the structured result.  A successful
    process without that artifact is deliberately invalid rather than guessed
    from terminal output.
    """

    def __init__(
        self,
        executable: str = "mutmut",
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self.executable = executable
        self._runner = runner
        self._which = which

    def available(self) -> bool:
        return self._which(self.executable) is not None

    def command(self, target: str | Path) -> tuple[str, ...]:
        return (self.executable, "run", "--paths-to-mutate", str(target))

    def execute(
        self,
        target: str | Path,
        *,
        cwd: str | Path,
        timeout_seconds: float,
        result_path: str | Path,
    ) -> tuple[MutationResult, MutationCommandEvidence]:
        command = self.command(target)
        if not self.available():
            return self._invalid(), MutationCommandEvidence(command, None, False, "", "mutmut executable not found")
        try:
            process = self._runner(
                list(command), cwd=str(cwd), text=True, capture_output=True,
                timeout=timeout_seconds, check=False,
            )
        except subprocess.TimeoutExpired as error:
            return self._invalid(), MutationCommandEvidence(
                command, None, True, self._text(error.stdout), self._text(error.stderr)
            )
        evidence = MutationCommandEvidence(
            command, process.returncode, False, process.stdout or "", process.stderr or ""
        )
        if process.returncode != 0:
            return self._invalid(), evidence
        try:
            return self.parse_result(Path(result_path)), evidence
        except (OSError, ValueError, json.JSONDecodeError):
            return self._invalid(), evidence

    @staticmethod
    def parse_result(path: Path) -> MutationResult:
        """Normalize the documented reporter artifact, rejecting malformed data."""
        raw = json.loads(path.read_text(encoding="utf-8"))
        required = {"killed", "survived", "timeout"}
        if not required.issubset(raw):
            raise ValueError("mutation result missing required counters")
        killed, survived, timed_out = (raw[name] for name in ("killed", "survived", "timeout"))
        if any(not isinstance(value, int) or value < 0 for value in (killed, survived, timed_out)):
            raise ValueError("mutation result counters must be non-negative integers")
        survivors = raw.get("survivors", [])
        if not isinstance(survivors, list) or any(not isinstance(item, dict) or not item.get("id", item.get("mutant_id")) for item in survivors):
            raise ValueError("mutation result survivors must have stable identifiers")
        normalized = tuple(
            {**item, "id": item["id"] if item.get("id") else item["mutant_id"]}
            for item in survivors
        )
        if len(normalized) > survived:
            raise ValueError("survivor records exceed survived counter")
        total = killed + survived + timed_out
        return MutationResult(total, killed, survived, timed_out, False, normalized)

    @staticmethod
    def _invalid() -> MutationResult:
        return MutationResult(0, 0, 0, 0, True)

    @staticmethod
    def _text(value: str | bytes | None) -> str:
        if isinstance(value, bytes):
            return value.decode(errors="replace")
        return value or ""
