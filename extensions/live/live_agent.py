"""Opt-in live wiring for AWS Bedrock + Databricks. Not imported by tests or CI.

Run (after `pip install -e '.[live]'` and exporting the variables below):

    AWS_REGION=us-west-2 BEDROCK_MODEL_ID=<a model or inference-profile id enabled in your account> \
    DATABRICKS_HOST=https://<workspace>.cloud.databricks.com DATABRICKS_TOKEN=... \
    DATABRICKS_WAREHOUSE_ID=... DATABRICKS_VECTOR_INDEX=main.support.policy_index \
    PYTHONPATH=src python extensions/live/live_agent.py --run

Without --run it prints the resolved wiring and exits (dry run). Payments stay fake on
purpose: never point a workshop at a real money-moving API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Any

from agentic_stack.agent import FakePayments, RefundAgent
from agentic_stack.bedrock import BedrockConverseModel
from agentic_stack.databricks import DatabricksTools
from agentic_stack.models import AgentRequest
from agentic_stack.tracing import JsonlExporter, Tracer, render_tree

REQUIRED = [
    "AWS_REGION",
    "BEDROCK_MODEL_ID",
    "DATABRICKS_HOST",
    "DATABRICKS_TOKEN",
    "DATABRICKS_WAREHOUSE_ID",
    "DATABRICKS_VECTOR_INDEX",
]


def databricks_http(host: str, token: str):
    """HttpCaller backed by the Databricks REST API (PAT or OAuth bearer token)."""

    def call(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            host.rstrip("/") + path,
            data=json.dumps(body).encode(),
            method=method,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())

    return call


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="actually call AWS and Databricks")
    parser.add_argument("--customer", default="C-01")
    parser.add_argument("--order", default="O-1001")
    parser.add_argument("--message", default="My dinner set arrived cracked.")
    args = parser.parse_args()

    missing = [k for k in REQUIRED if not os.environ.get(k)]
    print("wiring: Bedrock Converse model", os.environ.get("BEDROCK_MODEL_ID", "<unset>"))
    print("        Databricks warehouse", os.environ.get("DATABRICKS_WAREHOUSE_ID", "<unset>"))
    if missing:
        print(f"missing env: {missing}", file=sys.stderr)
        return 2
    if not args.run:
        print("dry run; pass --run to call live services")
        return 0

    import boto3  # imported lazily so the default path never needs it

    model = BedrockConverseModel(
        boto3.client("bedrock-runtime", region_name=os.environ["AWS_REGION"]),
        os.environ["BEDROCK_MODEL_ID"],
    )
    data = DatabricksTools(
        databricks_http(os.environ["DATABRICKS_HOST"], os.environ["DATABRICKS_TOKEN"]),
        warehouse_id=os.environ["DATABRICKS_WAREHOUSE_ID"],
        vector_index=os.environ["DATABRICKS_VECTOR_INDEX"],
    )
    tracer = Tracer(JsonlExporter("reports/live-traces.jsonl"))
    agent = RefundAgent(data, model, FakePayments(), tracer)
    result = agent.start(AgentRequest("live-1", args.customer, args.order, args.message))
    print(json.dumps(result.to_dict(), indent=2))
    print(render_tree(tracer.finished))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
