# Architecture and production seams

## Request path

1. `RefundAgent.start(request)` creates a workflow id `refund-<request_id>` and runs the
   deterministic workflow inside a root `AGENT` span.
2. **lookup_order** (activity, `TOOL` span) — `DatabricksTools.get_order` validates the order id
   format, then calls the SQL Statement Execution API with named markers `:order_id` and
   `:customer_id`. Customer scoping happens in SQL, so a user can't read someone else's order by
   guessing ids.
3. **retrieve_policies** (activity, `RETRIEVER` span) — Vector Search query, top-k bounded to 10;
   doc ids and scores are recorded as `retrieval.documents.N.document.*`.
4. **plan_decision** (activity, `LLM` + `GUARDRAIL` spans) — Bedrock Converse with bounded
   `maxTokens`/`temperature`. Output goes through `parse_decision`, which fails closed to
   `escalate` if the JSON is invalid, the action is unknown, a citation wasn't retrieved, or the
   amount is outside the order total.
5. **approval** — refunds above `APPROVAL_THRESHOLD` (POL-APPROVAL, $250) call
   `wait_for_signal("approval")`. The workflow state is persisted and the call returns
   `awaiting_approval`. A later `signal()` replays history: completed activities return recorded
   results; nothing is re-queried or re-billed.
6. **issue_refund** (activity, `TOOL` span) — retried with backoff; the idempotency key is
   `<workflow_id>:refund`, so retries or duplicate deliveries move money at most once.

## Where each partner fits in production

| Concern | Local seam | Production mapping |
|---|---|---|
| Inference | `ConverseClient` protocol | `boto3.client("bedrock-runtime").converse` |
| Agent hosting | `RefundAgent` + CLI | Amazon Bedrock AgentCore Runtime, ECS/Fargate, or Lambda behind API Gateway |
| Data | `HttpCaller` | Databricks SQL warehouse + Unity Catalog grants; Vector Search index on policy docs |
| Durability | `DurableRun` | Temporal Cloud or self-hosted Temporal; workers on ECS/EKS |
| Observability | `Tracer` + exporter | OpenTelemetry → Arize AX or Phoenix; OpenInference conventions |
| Release | `release_gate` | CI step before deploy (GitHub Actions / CodePipeline) |

## Invariants the tests enforce

- No SQL string formatting; unbound markers and multi-statements are rejected.
- Model output never moves money unless validated, cited, bounded, and (if large) approved.
- Workflow replay never re-runs a completed side effect; changed workflow code is detected as
  nondeterminism.
- Prompt/response content is redacted by default; emails and card numbers are scrubbed always.
- A broken telemetry exporter cannot fail a request.
- A release fails without passing evals, a digest-pinned image, and a named prod approver.
