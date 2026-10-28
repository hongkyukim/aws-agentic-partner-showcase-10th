"""Opt-in: replay the workshop's OpenInference-style spans into OpenTelemetry for Arize.

Two targets, pick one:

    # Arize AX (cloud)
    ARIZE_SPACE_ID=... ARIZE_API_KEY=... PYTHONPATH=src python extensions/live/arize_bridge.py --target arize
    # Phoenix (self-hosted / local: `pip install arize-phoenix && phoenix serve`)
    PYTHONPATH=src python extensions/live/arize_bridge.py --target phoenix

`register()` signatures change between releases - check the arize-otel / arize-phoenix-otel
docs for your installed version if this file errors at import or registration time.

In a real service you would instrument with OpenTelemetry spans directly (or an
OpenInference auto-instrumentor) instead of replaying; replay keeps this lab offline-first
and shows that the attribute names are the contract.
"""

from __future__ import annotations

import argparse
import os

from opentelemetry import trace

from agentic_stack.agent import build_local_agent
from agentic_stack.models import AgentRequest
from agentic_stack.tracing import Span, Tracer

PROJECT = "aws-agentic-showcase-10"


def tracer_provider(target: str):
    if target == "arize":
        from arize.otel import register

        return register(
            space_id=os.environ["ARIZE_SPACE_ID"],
            api_key=os.environ["ARIZE_API_KEY"],
            project_name=PROJECT,
        )
    from phoenix.otel import register

    return register(project_name=PROJECT, endpoint=os.environ.get("PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces"))


def replay(spans: list[Span], provider) -> None:
    otel = provider.get_tracer("agentic_stack.bridge")
    live: dict[str, trace.Span] = {}
    for s in sorted(spans, key=lambda s: s.start_ns):
        parent = live.get(s.parent_id) if s.parent_id else None
        ctx = trace.set_span_in_context(parent) if parent else None
        attrs = {k: v for k, v in s.to_dict()["attributes"].items() if v is not None and not isinstance(v, (dict, list))}
        live[s.span_id] = otel.start_span(s.name, context=ctx, start_time=s.start_ns, attributes=attrs)
        if s.status == "ERROR":
            live[s.span_id].set_status(trace.Status(trace.StatusCode.ERROR))
    for s in spans:
        live[s.span_id].end(end_time=s.end_ns)
    provider.force_flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["arize", "phoenix"], default="phoenix")
    args = parser.parse_args()

    tracer = Tracer(capture_content=True)  # PII is still scrubbed
    agent = build_local_agent(transient_payment_failures=1, tracer=tracer)
    r = agent.start(AgentRequest("arize-1", "C-02", "O-1002", "Monitor arrived broken"))
    agent.signal(r.workflow_id, "approval", {"approved": True, "approver": "lead-ana"})
    agent.start(AgentRequest("arize-2", "C-03", "O-1003", "Shoes are defective"))

    replay(tracer.finished, tracer_provider(args.target))
    print(f"exported {len(tracer.finished)} spans to {args.target} project {PROJECT!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
