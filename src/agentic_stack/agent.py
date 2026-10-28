"""The refund-exception agent: AWS model + Databricks data + Temporal-style workflow + Arize tracing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .bedrock import BedrockConverseModel, FakeBedrockClient, parse_decision, render_context
from .databricks import DatabricksTools, FakeDatabricksHttp
from .models import AgentRequest, AgentResult, Order, PolicyChunk
from .tracing import Tracer
from .workflow import DurableRun, NonRetryableError, RetryPolicy, WorkflowBlocked, WorkflowStore

APPROVAL_THRESHOLD = 250.0


@dataclass
class FakePayments:
    """Payment service with idempotency keys and injectable transient failures."""

    transient_failures: int = 0
    refunds: dict[str, dict[str, Any]] = field(default_factory=dict)
    attempts: int = 0

    def refund(self, order_id: str, amount: float, idempotency_key: str) -> dict[str, Any]:
        self.attempts += 1
        if amount <= 0:
            raise NonRetryableError("refund amount must be positive")
        if self.transient_failures > 0:
            self.transient_failures -= 1
            raise ConnectionError("payment gateway timeout")
        if idempotency_key not in self.refunds:
            refund_id = "RF-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:10]
            self.refunds[idempotency_key] = {"refund_id": refund_id, "order_id": order_id, "amount": amount}
        return self.refunds[idempotency_key]

    @property
    def money_movements(self) -> int:
        return len(self.refunds)


class RefundAgent:
    def __init__(
        self,
        data: DatabricksTools,
        model: BedrockConverseModel,
        payments: FakePayments,
        tracer: Tracer,
        *,
        store: WorkflowStore | None = None,
        approval_threshold: float = APPROVAL_THRESHOLD,
    ):
        self.data = data
        self.model = model
        self.payments = payments
        self.tracer = tracer
        self.store = store or WorkflowStore()
        self.approval_threshold = approval_threshold
        self.last_run: DurableRun | None = None

    # ---- public API ------------------------------------------------------
    def start(self, request: AgentRequest) -> AgentResult:
        workflow_id = f"refund-{request.request_id}"
        return self._run(workflow_id, request.to_dict(), [])

    def signal(self, workflow_id: str, name: str, payload: dict[str, Any]) -> AgentResult:
        workflow_input, history = self.store.load(workflow_id)
        run = DurableRun(workflow_id, history)
        run.signal(name, payload)
        return self._run(workflow_id, workflow_input, run.history)

    # ---- activities (all side effects live here) -------------------------
    def _lookup_order(self, order_id: str, customer_id: str) -> dict[str, Any] | None:
        with self.tracer.span("databricks.sql.get_order", "TOOL", tool__name="get_order", input__value=order_id) as s:
            order = self.data.get_order(order_id, customer_id)
            s.set("output.value", order.to_dict() if order else None)
            return order.to_dict() if order else None

    def _retrieve_policies(self, message: str, order: dict[str, Any] | None) -> list[dict[str, Any]]:
        status = order["status"] if order else "unknown"
        query = f"{message} refund {status} 30 days delivery approval"
        with self.tracer.span("databricks.vector_search", "RETRIEVER", input__value=query) as s:
            chunks = self.data.search_policies(query, k=3)
            for i, c in enumerate(chunks):
                s.set(f"retrieval.documents.{i}.document.id", c.doc_id)
                s.set(f"retrieval.documents.{i}.document.score", c.score)
            return [c.to_dict() for c in chunks]

    def _plan(self, message: str, order: dict[str, Any] | None, policies: list[dict[str, Any]]) -> dict[str, Any]:
        order_obj = Order(**order) if order else None
        chunks = [PolicyChunk(**p) for p in policies]
        prompt = render_context(message, order_obj, chunks)
        with self.tracer.span("bedrock.converse", "LLM", llm__model_name=self.model.model_id, input__value=prompt) as s:
            reply = self.model.complete(prompt)
            s.set("output.value", reply.text)
            s.set("llm.token_count.prompt", reply.input_tokens)
            s.set("llm.token_count.completion", reply.output_tokens)
            s.set("llm.token_count.total", reply.input_tokens + reply.output_tokens)
        with self.tracer.span("guardrail.validate_decision", "GUARDRAIL") as g:
            decision = parse_decision(reply.text, order_obj, chunks)
            g.set("guardrail.action", decision.action)
            g.set("guardrail.reason", decision.reason)
        return decision.to_dict()

    def _issue_refund(self, order_id: str, amount: float, idempotency_key: str) -> dict[str, Any]:
        with self.tracer.span("payments.refund", "TOOL", tool__name="issue_refund") as s:
            s.set("refund.amount", amount)
            return self.payments.refund(order_id, amount, idempotency_key)

    # ---- deterministic workflow -----------------------------------------
    def _workflow(self, run: DurableRun, req: dict[str, Any]) -> dict[str, Any]:
        order = run.execute_activity("lookup_order", self._lookup_order, req["order_id"], req["customer_id"])
        policies = run.execute_activity("retrieve_policies", self._retrieve_policies, req["message"], order)
        decision = run.execute_activity("plan_decision", self._plan, req["message"], order, policies)
        notes: list[str] = []

        if decision["action"] == "refund" and decision["amount"] > self.approval_threshold:
            approval = run.wait_for_signal("approval")
            notes.append(f"approval by {approval.get('approver', 'unknown')}: {approval.get('approved')}")
            if not approval.get("approved"):
                decision = {**decision, "action": "deny", "amount": 0.0, "reason": "support lead rejected refund"}

        refund = None
        if decision["action"] == "refund":
            refund = run.execute_activity(
                "issue_refund",
                self._issue_refund,
                req["order_id"],
                decision["amount"],
                f"{run.workflow_id}:refund",
                retry=RetryPolicy(maximum_attempts=4, initial_interval_s=0.2),
            )
        return {"decision": decision, "refund": refund, "notes": notes}

    def _run(self, workflow_id: str, req: dict[str, Any], history: list[dict[str, Any]]) -> AgentResult:
        run = DurableRun(workflow_id, history)
        self.last_run = run
        with self.tracer.span("refund_agent", "AGENT", input__value=req["message"]) as root:
            root.set("workflow.id", workflow_id)
            root.set("session.id", req["customer_id"])
            try:
                out = self._workflow(run, req)
            except WorkflowBlocked as blocked:
                root.set("workflow.status", f"awaiting:{blocked.signal_name}")
                self.store.save(workflow_id, req, run.history)
                return AgentResult(
                    request_id=req["request_id"],
                    workflow_id=workflow_id,
                    status="awaiting_approval",
                    trace_id=root.trace_id,
                    history_length=len(run.history),
                    notes=[f"waiting for signal '{blocked.signal_name}'"],
                )
            root.set("workflow.status", "completed")
            root.set("output.value", out["decision"])
        self.store.save(workflow_id, req, run.history)
        return AgentResult(
            request_id=req["request_id"],
            workflow_id=workflow_id,
            status="completed",
            decision=out["decision"],
            refund_id=out["refund"]["refund_id"] if out["refund"] else None,
            trace_id=root.trace_id,
            history_length=len(run.history),
            notes=out["notes"],
        )


def build_local_agent(
    *,
    misbehave: str | None = None,
    transient_payment_failures: int = 0,
    tracer: Tracer | None = None,
) -> RefundAgent:
    """Credential-free wiring. Swap each fake for a live client - see docs/live-providers.md."""
    data = DatabricksTools(FakeDatabricksHttp(), warehouse_id="local-warehouse", vector_index="main.support.policy_index")
    model = BedrockConverseModel(FakeBedrockClient(misbehave=misbehave), model_id="local-fake-model")
    payments = FakePayments(transient_failures=transient_payment_failures)
    return RefundAgent(data, model, payments, tracer or Tracer())
