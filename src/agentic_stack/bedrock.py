"""AWS seam: Amazon Bedrock Converse API adapter.

The adapter only depends on an object with a ``converse(**request)`` method, which is
exactly the shape of ``boto3.client("bedrock-runtime")``. The default demo injects
``FakeBedrockClient`` so the same request/response code path runs without AWS.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from .models import Decision, Order, PolicyChunk

MAX_TOKENS_CEILING = 2048
ALLOWED_ACTIONS = {"refund", "deny", "escalate"}

SYSTEM_PROMPT = (
    "You are a refund-exception agent. Decide refund, deny, or escalate using ONLY the "
    "provided order and policy context. Reply with a single JSON object: "
    '{"action": str, "amount": number, "reason": str, "citations": [policy doc_id, ...]}. '
    "Never invent policy text. Cite every policy you rely on."
)


class ConverseClient(Protocol):
    def converse(self, **request: Any) -> dict[str, Any]: ...


def build_converse_request(
    model_id: str,
    system: str,
    user_text: str,
    *,
    max_tokens: int = 512,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """Build a bounded Bedrock Converse request payload."""
    if not model_id:
        raise ValueError("model_id is required")
    if not 1 <= max_tokens <= MAX_TOKENS_CEILING:
        raise ValueError(f"max_tokens must be in [1, {MAX_TOKENS_CEILING}]")
    if not 0.0 <= temperature <= 1.0:
        raise ValueError("temperature must be in [0, 1]")
    return {
        "modelId": model_id,
        "system": [{"text": system}],
        "messages": [{"role": "user", "content": [{"text": user_text}]}],
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }


def render_context(request_message: str, order: Order | None, policies: list[PolicyChunk]) -> str:
    context = {
        "customer_message": request_message,
        "order": order.to_dict() if order else None,
        "policies": [p.to_dict() for p in policies],
    }
    return "CONTEXT:\n" + json.dumps(context, sort_keys=True)


@dataclass
class ModelReply:
    text: str
    stop_reason: str
    input_tokens: int
    output_tokens: int


class BedrockConverseModel:
    def __init__(self, client: ConverseClient, model_id: str, *, max_tokens: int = 512):
        self.client = client
        self.model_id = model_id
        self.max_tokens = max_tokens

    def complete(self, user_text: str, system: str = SYSTEM_PROMPT) -> ModelReply:
        request = build_converse_request(self.model_id, system, user_text, max_tokens=self.max_tokens)
        response = self.client.converse(**request)
        blocks = response["output"]["message"]["content"]
        text = "".join(block.get("text", "") for block in blocks)
        usage = response.get("usage", {})
        return ModelReply(
            text=text,
            stop_reason=response.get("stopReason", "unknown"),
            input_tokens=int(usage.get("inputTokens", 0)),
            output_tokens=int(usage.get("outputTokens", 0)),
        )


def parse_decision(text: str, order: Order | None, policies: list[PolicyChunk]) -> Decision:
    """Validate model output; fail closed to `escalate` on anything suspicious."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return Decision("escalate", 0.0, "model output was not JSON")
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return Decision("escalate", 0.0, "model output was not valid JSON")

    action = raw.get("action")
    if action not in ALLOWED_ACTIONS:
        return Decision("escalate", 0.0, f"unknown action {action!r}")
    try:
        amount = round(float(raw.get("amount", 0.0)), 2)
    except (TypeError, ValueError):
        return Decision("escalate", 0.0, "amount was not numeric")
    citations = tuple(str(c) for c in raw.get("citations", []))
    known = {p.doc_id for p in policies}
    if not set(citations) <= known:
        return Decision("escalate", 0.0, "model cited policy that was not retrieved")
    if action == "refund":
        if order is None or not 0 < amount <= order.amount:
            return Decision("escalate", 0.0, "refund amount outside order bounds")
        if not citations:
            return Decision("escalate", 0.0, "refund without a policy citation")
    if action != "refund":
        amount = 0.0
    return Decision(action, amount, str(raw.get("reason", ""))[:500], citations)


class FakeBedrockClient:
    """Deterministic stand-in that returns Converse-shaped responses.

    It applies the workshop refund policy to the CONTEXT block so the rest of the
    stack (validation, workflow, tracing, evals) is exercised realistically.
    """

    def __init__(self, *, misbehave: str | None = None):
        self.requests: list[dict[str, Any]] = []
        self.misbehave = misbehave  # "hallucinate" | "garbage" | "overpay" | None

    def converse(self, **request: Any) -> dict[str, Any]:
        self.requests.append(request)
        user_text = request["messages"][-1]["content"][0]["text"]
        context = json.loads(user_text.split("CONTEXT:\n", 1)[1])
        decision = self._decide(context)
        text = "garbage output" if self.misbehave == "garbage" else json.dumps(decision)
        return {
            "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
            "stopReason": "end_turn",
            "usage": {
                "inputTokens": len(user_text) // 4,
                "outputTokens": len(text) // 4,
                "totalTokens": (len(user_text) + len(text)) // 4,
            },
        }

    def _decide(self, context: dict[str, Any]) -> dict[str, Any]:
        order = context["order"]
        policy_ids = [p["doc_id"] for p in context["policies"]]
        message = context["customer_message"].lower()
        if self.misbehave == "hallucinate":
            return {"action": "refund", "amount": 1.0, "reason": "trust me", "citations": ["POL-999"]}
        if order is None:
            return {"action": "deny", "amount": 0, "reason": "order not found", "citations": []}
        if self.misbehave == "overpay":
            return {"action": "refund", "amount": order["amount"] * 10, "reason": "x", "citations": policy_ids[:1]}
        damaged = any(word in message for word in ("damaged", "broken", "defective", "cracked"))
        if order["status"] != "delivered":
            return {"action": "escalate", "amount": 0, "reason": "order not delivered yet", "citations": []}
        if damaged and order["days_since_delivery"] <= 30 and "POL-DAMAGE" in policy_ids:
            return {
                "action": "refund",
                "amount": order["amount"],
                "reason": "damaged on arrival within 30 days",
                "citations": ["POL-DAMAGE"],
            }
        if order["days_since_delivery"] > 30 and "POL-WINDOW" in policy_ids:
            return {"action": "deny", "amount": 0, "reason": "outside 30-day window", "citations": ["POL-WINDOW"]}
        return {"action": "escalate", "amount": 0, "reason": "needs human review", "citations": []}
