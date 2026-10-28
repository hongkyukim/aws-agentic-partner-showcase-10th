"""Arize seam: OpenInference-style tracing with redaction and safe export.

Spans use OpenInference semantic-convention attribute names (``openinference.span.kind``,
``input.value``, ``llm.token_count.prompt``, ``tool.name``, ...) so the same records can
be bridged into OpenTelemetry and sent to Arize AX or Phoenix
(see ``extensions/live/arize_bridge.py``).

Production rules encoded here:
* Prompt/response content is redacted unless ``capture_content=True``.
* PII patterns (emails, card-like numbers) are scrubbed even when content is captured.
* Exporter failures are counted, never raised into the request path.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

SPAN_KINDS = {"AGENT", "CHAIN", "LLM", "TOOL", "RETRIEVER", "EVALUATOR", "GUARDRAIL"}
CONTENT_KEYS = {"input.value", "output.value"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")

Exporter = Callable[[list[dict[str, Any]]], None]


def scrub(text: str) -> str:
    return CARD.sub("[CARD]", EMAIL.sub("[EMAIL]", text))


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_id: str | None
    kind: str
    start_ns: int
    end_ns: int | None = None
    status: str = "OK"
    attributes: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "context.trace_id": self.trace_id,
            "context.span_id": self.span_id,
            "parent_id": self.parent_id,
            "start_time_ns": self.start_ns,
            "end_time_ns": self.end_ns,
            "status_code": self.status,
            "attributes": {"openinference.span.kind": self.kind, **self.attributes},
        }


class Tracer:
    def __init__(self, exporter: Exporter | None = None, *, capture_content: bool = False, project: str = "showcase-10"):
        self.exporter = exporter
        self.capture_content = capture_content
        self.project = project
        self.finished: list[Span] = []
        self.export_failures = 0
        self._stack: list[Span] = []

    def _clean(self, key: str, value: Any) -> Any:
        if key in CONTENT_KEYS:
            if not self.capture_content:
                return "[REDACTED]"
            return scrub(value if isinstance(value, str) else json.dumps(value, sort_keys=True))
        if isinstance(value, str):
            return scrub(value)
        return value

    @contextmanager
    def span(self, name: str, kind: str, **attributes: Any) -> Iterator[Span]:
        if kind not in SPAN_KINDS:
            raise ValueError(f"unknown span kind {kind}")
        parent = self._stack[-1] if self._stack else None
        span = Span(
            name=name,
            trace_id=parent.trace_id if parent else secrets.token_hex(16),
            span_id=secrets.token_hex(8),
            parent_id=parent.span_id if parent else None,
            kind=kind,
            start_ns=time.time_ns(),
        )
        for k, v in attributes.items():
            span.set(k.replace("__", "."), self._clean(k.replace("__", "."), v))
        self._stack.append(span)
        try:
            yield span
        except Exception as exc:
            span.status = "ERROR"
            span.set("exception.type", type(exc).__name__)
            raise
        finally:
            span.end_ns = time.time_ns()
            span.attributes = {k: self._clean(k, v) for k, v in span.attributes.items()}
            self._stack.pop()
            self.finished.append(span)
            if parent is None:
                self.flush([s for s in self.finished if s.trace_id == span.trace_id])

    def flush(self, spans: list[Span]) -> None:
        if not self.exporter:
            return
        try:
            self.exporter([s.to_dict() for s in spans])
        except Exception:  # telemetry must never break the request path
            self.export_failures += 1


class JsonlExporter:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def __call__(self, spans: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            for span in spans:
                fh.write(json.dumps(span, sort_keys=True) + "\n")


def render_tree(spans: list[Span]) -> str:
    children: dict[str | None, list[Span]] = {}
    for s in sorted(spans, key=lambda s: s.start_ns):
        children.setdefault(s.parent_id, []).append(s)
    lines: list[str] = []

    def walk(parent: str | None, depth: int) -> None:
        for s in children.get(parent, []):
            ms = ((s.end_ns or s.start_ns) - s.start_ns) / 1e6
            lines.append(f"{'  ' * depth}- [{s.kind}] {s.name} ({ms:.1f} ms, {s.status})")
            walk(s.span_id, depth + 1)

    walk(None, 0)
    return "\n".join(lines)
