# Going live: replace one object per partner

Everything below is opt-in. `pip install -e '.[live]'` first. Never commit credentials; use your
shell, AWS profiles/SSO, or a secrets manager.

## AWS — Amazon Bedrock

Replace `FakeBedrockClient()` with `boto3.client("bedrock-runtime", region_name=...)` and pass a
model id or inference-profile id that is enabled in your account:

```python
model = BedrockConverseModel(boto3.client("bedrock-runtime", region_name="us-west-2"), os.environ["BEDROCK_MODEL_ID"])
```

`BedrockConverseModel` calls `client.converse(**request)` and reads
`output.message.content[].text`, `stopReason`, and `usage.inputTokens/outputTokens`. IAM needs
`bedrock:InvokeModel` on the chosen model. Keep `parse_decision` in place — the guardrail is
model-agnostic. You can add Amazon Bedrock Guardrails on top via the Converse `guardrailConfig`.

## Databricks

Replace `FakeDatabricksHttp()` with an authenticated caller (see
`extensions/live/live_agent.py::databricks_http`). Create:

- table `main.support.orders(order_id, customer_id, item, amount, status, days_since_delivery)`
  — seed rows are in `databricks.ORDERS`;
- a Vector Search index (name in `DATABRICKS_VECTOR_INDEX`) over policy docs with columns
  `doc_id`, `text` — seed text is in `databricks.POLICIES`.

Grant the agent's service principal `SELECT` on the table only (Unity Catalog). Check that the
Vector Search query response in your workspace matches what `search_policies` parses (it reads
`manifest.columns` and appends `score`); adjust there if your index type differs.

## Temporal

`extensions/live/temporal_worker.py` is the same workflow on the real `temporalio` SDK:
activities with `start_to_close_timeout` and `RetryPolicy`, an `approve` signal, and
`workflow.wait_condition` for the approval wait. Start a dev server with the Temporal CLI
(`temporal server start-dev`, UI at http://localhost:8233) or point `--address` at Temporal
Cloud (which also needs namespace + mTLS/API key options on `Client.connect`).

## Arize

`extensions/live/arize_bridge.py` replays workshop spans into OpenTelemetry using
`arize.otel.register(...)` (Arize AX: `ARIZE_SPACE_ID`, `ARIZE_API_KEY`) or
`phoenix.otel.register(...)` (local Phoenix). In a service you'd create OTel spans directly with
the same attribute names, or use an OpenInference auto-instrumentor for your framework. Upload
`reports/eval.json` rows (`eval.correctness.label/score`, `context.trace_id`) to attach evals to
traces.

## What stays fake

`FakePayments`. Moving real money is out of scope for a workshop; the idempotency and approval
patterns are what transfer.
