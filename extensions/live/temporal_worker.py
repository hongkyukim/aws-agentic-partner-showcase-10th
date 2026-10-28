"""Opt-in: the same refund workflow on a real Temporal cluster (temporalio Python SDK).

    # terminal 1 - local dev server (Temporal CLI)
    temporal server start-dev
    # terminal 2 - worker
    PYTHONPATH=src python extensions/live/temporal_worker.py worker
    # terminal 3 - start a large refund, then approve it
    PYTHONPATH=src python extensions/live/temporal_worker.py start --id refund-live-2 \
        --customer C-02 --order O-1002 --message "The monitor arrived with a broken screen."
    PYTHONPATH=src python extensions/live/temporal_worker.py approve --id refund-live-2 --approver lead-ana

Kill the worker while the workflow is waiting for approval and restart it: the
workflow resumes from event history. Compare with tests/test_temporal_workflow.py.

Activities reuse the local fakes so the lab is credential-free; swap them for the live
clients from extensions/live/live_agent.py to go further.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
from typing import Any

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import Worker

with workflow.unsafe.imports_passed_through():
    from agentic_stack.agent import APPROVAL_THRESHOLD, build_local_agent

TASK_QUEUE = "refund-agent"
_agent = None


def agent():
    global _agent
    if _agent is None:
        _agent = build_local_agent(transient_payment_failures=1)
    return _agent


@activity.defn
async def lookup_order(order_id: str, customer_id: str) -> dict[str, Any] | None:
    return agent()._lookup_order(order_id, customer_id)


@activity.defn
async def retrieve_policies(message: str, order: dict[str, Any] | None) -> list[dict[str, Any]]:
    return agent()._retrieve_policies(message, order)


@activity.defn
async def plan_decision(message: str, order: dict[str, Any] | None, policies: list[dict[str, Any]]) -> dict[str, Any]:
    return agent()._plan(message, order, policies)


@activity.defn
async def issue_refund(order_id: str, amount: float, idempotency_key: str) -> dict[str, Any]:
    return agent()._issue_refund(order_id, amount, idempotency_key)


@workflow.defn
class RefundWorkflow:
    def __init__(self) -> None:
        self._approval: dict[str, Any] | None = None

    @workflow.signal
    def approve(self, approval: dict[str, Any]) -> None:
        self._approval = approval

    @workflow.run
    async def run(self, req: dict[str, Any]) -> dict[str, Any]:
        opts = {"start_to_close_timeout": timedelta(seconds=30), "retry_policy": RetryPolicy(maximum_attempts=3)}
        order = await workflow.execute_activity(lookup_order, args=[req["order_id"], req["customer_id"]], **opts)
        policies = await workflow.execute_activity(retrieve_policies, args=[req["message"], order], **opts)
        decision = await workflow.execute_activity(plan_decision, args=[req["message"], order, policies], **opts)

        if decision["action"] == "refund" and decision["amount"] > APPROVAL_THRESHOLD:
            await workflow.wait_condition(lambda: self._approval is not None, timeout=timedelta(days=3))
            if not self._approval.get("approved"):
                decision = {**decision, "action": "deny", "amount": 0.0, "reason": "support lead rejected refund"}

        refund = None
        if decision["action"] == "refund":
            refund = await workflow.execute_activity(
                issue_refund,
                args=[req["order_id"], decision["amount"], f"{workflow.info().workflow_id}:refund"],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=5, initial_interval=timedelta(milliseconds=200)),
            )
        return {"decision": decision, "refund": refund}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["worker", "start", "approve", "reject"])
    parser.add_argument("--address", default="localhost:7233")
    parser.add_argument("--id", default="refund-live-1")
    parser.add_argument("--customer", default="C-01")
    parser.add_argument("--order", default="O-1001")
    parser.add_argument("--message", default="My dinner set arrived cracked.")
    parser.add_argument("--approver", default="lead")
    args = parser.parse_args()

    client = await Client.connect(args.address)
    if args.command == "worker":
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[RefundWorkflow],
            activities=[lookup_order, retrieve_policies, plan_decision, issue_refund],
        )
        print(f"worker polling task queue {TASK_QUEUE!r}")
        await worker.run()
    elif args.command == "start":
        req = {"request_id": args.id, "customer_id": args.customer, "order_id": args.order, "message": args.message}
        handle = await client.start_workflow(RefundWorkflow.run, req, id=args.id, task_queue=TASK_QUEUE)
        print(f"started {handle.id}; open http://localhost:8233 to watch the event history")
    else:
        handle = client.get_workflow_handle(args.id)
        await handle.signal(RefundWorkflow.approve, {"approved": args.command == "approve", "approver": args.approver})
        print(await handle.result())


if __name__ == "__main__":
    asyncio.run(main())
