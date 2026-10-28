"""Temporal seam: a tiny durable-execution engine that teaches Temporal's model.

This is NOT Temporal. It is a ~150-line local model of the guarantees Temporal gives
you so attendees can see them in a unit test before running a real worker
(see ``extensions/live/temporal_worker.py``):

* Workflow code is deterministic; side effects run in *activities*.
* Every activity result is appended to an event history.
* Re-running a workflow with its history *replays* recorded results instead of
  re-executing side effects - that is how a crashed worker resumes.
* Activities retry with a policy; some errors are non-retryable.
* Workflows can block on a *signal* (human approval) for as long as needed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable


class NonRetryableError(Exception):
    """Raise from an activity to stop retries immediately."""


class WorkflowBlocked(Exception):
    """Raised inside workflow code when it must wait for a signal."""

    def __init__(self, signal_name: str):
        super().__init__(signal_name)
        self.signal_name = signal_name


class ActivityFailed(Exception):
    pass


class NondeterminismError(Exception):
    """Replay found a different command than the history recorded."""


@dataclass(frozen=True)
class RetryPolicy:
    maximum_attempts: int = 3
    initial_interval_s: float = 0.1
    backoff_coefficient: float = 2.0

    def delays(self) -> list[float]:
        return [self.initial_interval_s * self.backoff_coefficient**i for i in range(self.maximum_attempts - 1)]


@dataclass
class DurableRun:
    workflow_id: str
    history: list[dict[str, Any]] = field(default_factory=list)
    sleep: Callable[[float], None] = lambda _s: None
    _cursor: int = 0
    executed: list[str] = field(default_factory=list)  # activities actually run this pass

    def _next_recorded(self, kind: str, name: str) -> dict[str, Any] | None:
        """Return the next recorded completion for this command during replay."""
        while self._cursor < len(self.history):
            event = self.history[self._cursor]
            self._cursor += 1
            if event["type"] in {"ActivityScheduled", "ActivityAttemptFailed", "SignalReceived"}:
                continue
            if event["type"] != kind or event["name"] != name:
                raise NondeterminismError(
                    f"history has {event['type']}:{event['name']} but workflow issued {kind}:{name}"
                )
            return event
        return None

    def execute_activity(
        self, name: str, fn: Callable[..., Any], *args: Any, retry: RetryPolicy = RetryPolicy()
    ) -> Any:
        recorded = self._next_recorded("ActivityCompleted", name)
        if recorded is not None:
            return recorded["result"]

        self.history.append({"type": "ActivityScheduled", "name": name})
        delays = retry.delays()
        for attempt in range(1, retry.maximum_attempts + 1):
            try:
                result = fn(*args)
            except NonRetryableError as exc:
                self.history.append({"type": "ActivityAttemptFailed", "name": name, "attempt": attempt, "error": str(exc)})
                raise ActivityFailed(f"{name}: {exc}") from exc
            except Exception as exc:  # retryable by default, like Temporal
                self.history.append({"type": "ActivityAttemptFailed", "name": name, "attempt": attempt, "error": str(exc)})
                if attempt == retry.maximum_attempts:
                    raise ActivityFailed(f"{name} failed after {attempt} attempts: {exc}") from exc
                self.sleep(delays[attempt - 1])
                continue
            result = json.loads(json.dumps(result))  # histories must be serializable
            self.history.append({"type": "ActivityCompleted", "name": name, "attempt": attempt, "result": result})
            self._cursor = len(self.history)
            self.executed.append(name)
            return result
        raise AssertionError("unreachable")

    def wait_for_signal(self, name: str) -> Any:
        for event in self.history:
            if event["type"] == "SignalReceived" and event["name"] == name:
                return event["payload"]
        raise WorkflowBlocked(name)

    def signal(self, name: str, payload: Any) -> None:
        self.history.append({"type": "SignalReceived", "name": name, "payload": json.loads(json.dumps(payload))})


class WorkflowStore:
    """Keeps histories between runs. Swap for a file/DB to survive process restarts."""

    def __init__(self) -> None:
        self._histories: dict[str, list[dict[str, Any]]] = {}
        self._inputs: dict[str, dict[str, Any]] = {}

    def save(self, workflow_id: str, workflow_input: dict[str, Any], history: list[dict[str, Any]]) -> None:
        self._inputs[workflow_id] = workflow_input
        self._histories[workflow_id] = history

    def load(self, workflow_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if workflow_id not in self._histories:
            raise KeyError(f"unknown workflow {workflow_id}")
        return self._inputs[workflow_id], list(self._histories[workflow_id])
