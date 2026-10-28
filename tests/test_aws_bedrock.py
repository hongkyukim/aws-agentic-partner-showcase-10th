import pytest

from agentic_stack.bedrock import (
    BedrockConverseModel,
    FakeBedrockClient,
    build_converse_request,
    parse_decision,
)
from agentic_stack.models import Order, PolicyChunk

ORDER = Order("O-1001", "C-01", "dinner set", 89.0, "delivered", 3)
POLICIES = [PolicyChunk("POL-DAMAGE", "damaged items refundable", 0.9)]


def test_converse_request_shape_and_bounds():
    req = build_converse_request("model-x", "sys", "hello", max_tokens=256, temperature=0.2)
    assert req["modelId"] == "model-x"
    assert req["system"] == [{"text": "sys"}]
    assert req["messages"] == [{"role": "user", "content": [{"text": "hello"}]}]
    assert req["inferenceConfig"] == {"maxTokens": 256, "temperature": 0.2}


@pytest.mark.parametrize("kwargs", [{"max_tokens": 0}, {"max_tokens": 100_000}, {"temperature": 1.5}])
def test_converse_request_rejects_unbounded_settings(kwargs):
    with pytest.raises(ValueError):
        build_converse_request("model-x", "sys", "hi", **kwargs)


def test_model_parses_converse_response_and_usage():
    client = FakeBedrockClient()
    model = BedrockConverseModel(client, "model-x")
    reply = model.complete('CONTEXT:\n{"customer_message": "arrived broken", "order": null, "policies": []}')
    assert reply.stop_reason == "end_turn"
    assert reply.input_tokens > 0 and reply.output_tokens > 0
    assert client.requests[0]["modelId"] == "model-x"


@pytest.mark.parametrize(
    "text, reason_fragment",
    [
        ("not json", "not JSON"),
        ('{"action": "wire_money", "amount": 5}', "unknown action"),
        ('{"action": "refund", "amount": 89, "citations": ["POL-999"]}', "not retrieved"),
        ('{"action": "refund", "amount": 890, "citations": ["POL-DAMAGE"]}', "outside order bounds"),
        ('{"action": "refund", "amount": 89, "citations": []}', "without a policy citation"),
    ],
)
def test_guardrail_fails_closed_to_escalate(text, reason_fragment):
    decision = parse_decision(text, ORDER, POLICIES)
    assert decision.action == "escalate"
    assert decision.amount == 0.0
    assert reason_fragment in decision.reason


def test_valid_refund_passes_guardrail():
    decision = parse_decision('{"action": "refund", "amount": 89, "reason": "ok", "citations": ["POL-DAMAGE"]}', ORDER, POLICIES)
    assert decision.action == "refund" and decision.amount == 89.0
