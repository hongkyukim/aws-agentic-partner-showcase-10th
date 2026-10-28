import json

import pytest

from agentic_stack.agent import build_local_agent
from agentic_stack.models import AgentRequest
from agentic_stack.tracing import JsonlExporter, Tracer, scrub


def run_once(tracer):
    agent = build_local_agent(tracer=tracer)
    agent.start(AgentRequest("t1", "C-01", "O-1001", "arrived broken, mail ana@example.com card 4111 1111 1111 1111"))
    return agent


def test_spans_share_one_trace_and_use_openinference_kinds():
    tracer = Tracer()
    run_once(tracer)
    kinds = {s.attributes.get("openinference.span.kind") or s.kind for s in tracer.finished}
    assert {"AGENT", "TOOL", "RETRIEVER", "LLM", "GUARDRAIL"} <= kinds
    assert len({s.trace_id for s in tracer.finished}) == 1
    root = [s for s in tracer.finished if s.parent_id is None]
    assert len(root) == 1 and root[0].kind == "AGENT"
    assert all(s.parent_id == root[0].span_id for s in tracer.finished if s is not root[0])


def test_llm_span_records_model_and_token_counts():
    tracer = Tracer()
    run_once(tracer)
    llm = next(s for s in tracer.finished if s.kind == "LLM")
    assert llm.attributes["llm.model_name"] == "local-fake-model"
    assert llm.attributes["llm.token_count.total"] == (
        llm.attributes["llm.token_count.prompt"] + llm.attributes["llm.token_count.completion"]
    )


def test_content_is_redacted_by_default():
    tracer = Tracer()
    run_once(tracer)
    for span in tracer.finished:
        for key in ("input.value", "output.value"):
            if key in span.attributes:
                assert span.attributes[key] == "[REDACTED]"


def test_pii_is_scrubbed_even_when_content_capture_is_on(tmp_path):
    path = tmp_path / "traces.jsonl"
    tracer = Tracer(JsonlExporter(path), capture_content=True)
    run_once(tracer)
    text = path.read_text()
    assert "ana@example.com" not in text and "4111 1111 1111 1111" not in text
    assert "[EMAIL]" in text
    records = [json.loads(line) for line in text.splitlines()]
    assert all("context.trace_id" in r and "context.span_id" in r for r in records)


def test_exporter_failure_never_breaks_the_request():
    def broken_exporter(_spans):
        raise ConnectionError("collector down")

    tracer = Tracer(broken_exporter)
    agent = build_local_agent(tracer=tracer)
    result = agent.start(AgentRequest("t2", "C-01", "O-1001", "arrived cracked"))
    assert result.status == "completed"
    assert tracer.export_failures == 1


def test_errors_mark_span_status():
    tracer = Tracer()
    with pytest.raises(RuntimeError):
        with tracer.span("boom", "TOOL"):
            raise RuntimeError("x")
    assert tracer.finished[0].status == "ERROR"


def test_scrub():
    assert scrub("a@b.co 4242-4242-4242-4242") == "[EMAIL] [CARD]"
