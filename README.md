# AWS Agentic Partner Showcase Extended — 10th Edition Workshop

Hands-on companion repo for the **AWS Agentic Partner Showcase Extended (10th Edition)** with
experts from **AWS, Temporal, Arize, and Databricks**: building production-ready agentic AI
systems from code to deployment.

You build one agent and push it through the whole stack the talks cover:

| Layer | Partner | What you do in this repo |
|---|---|---|
| Model + deploy | **AWS** | Bounded Amazon Bedrock Converse requests, fail-closed output guardrail, release gate before AgentCore / ECS deploy |
| Data + retrieval | **Databricks** | Parameterized SQL Statement Execution calls, customer-scoped rows, Vector Search policy retrieval |
| Durable execution | **Temporal** | Activities, retries, idempotency, human-approval signal, crash-safe replay |
| Observability + evals | **Arize** | OpenInference-style traces, redaction, golden-set evals that block bad releases |

The use case: a **refund-exception agent** for an online store. Small, clearly-eligible refunds go
through automatically; refunds above $250 park durably until a support lead approves; anything the
model can't justify with retrieved policy is escalated instead of paid.

```
customer msg ─▶ [Temporal-style workflow] ─────────────────────────────────────────────▶ result
                  │ activity: lookup_order      → Databricks SQL (named params, scoped)
                  │ activity: retrieve_policies → Databricks Vector Search
                  │ activity: plan_decision     → Bedrock Converse → guardrail (fail closed)
                  │ wait_for_signal("approval") if amount > $250   ⏸ durable
                  │ activity: issue_refund      → payments (retry + idempotency key)
                  └─ every step is a span (AGENT/TOOL/RETRIEVER/LLM/GUARDRAIL) → Arize
evals on golden set ─▶ release gate (accuracy, groundedness, approvals, pinned image, prod approver)
```

The default path is **local and credential-free** (Python 3.11+, stdlib only). Every vendor
call goes through an injected client with the vendor's real request/response shape, so the
same code runs live by swapping one object — see `docs/live-providers.md`.

## Quick start (2 minutes)

```bash
git clone https://github.com/hongkyukim/aws-agentic-partner-showcase-10th.git
cd aws-agentic-partner-showcase-10th

make demo      # 3 scenarios: auto refund w/ flaky payments, durable approval, cross-customer attempt
make trace     # one trace tree + the redacted LLM span
make eval      # golden-set evals -> reports/eval.md
make gate      # release gate over reports/eval.json (PASS)
make eval-bad  # same evals with a hallucinating model ...
make gate      # ... gate now FAILS, and zero money moved
make test      # 38 contract tests (uses uv; or: pip install pytest && PYTHONPATH=src pytest)
```

No `make`? Use `PYTHONPATH=src python3 -m agentic_stack demo|trace|eval|gate`.

## Labs

| # | Lab | Partner | Time |
|---|---|---|---|
| 0 | [Setup and the baseline run](labs/00-setup.md) | — | 10 min |
| 1 | [Bedrock Converse + output guardrails](labs/01-aws-bedrock.md) | AWS | 15 min |
| 2 | [Governed data tools](labs/02-databricks-data.md) | Databricks | 15 min |
| 3 | [Durable agent workflows](labs/03-temporal-durability.md) | Temporal | 20 min |
| 4 | [Tracing and evals](labs/04-arize-observability.md) | Arize | 20 min |
| 5 | [Capstone: release gate to AWS](labs/05-capstone-release-gate.md) | AWS | 15 min |

Labs map onto the event agenda — see [docs/agenda.md](docs/agenda.md). Questions to bring to
the partner booths during networking are in [docs/booth-questions.md](docs/booth-questions.md).

## Repo layout

```
src/agentic_stack/
  bedrock.py      AWS: Converse request builder, model adapter, guardrail, fake client
  databricks.py   Databricks: SQL statement + Vector Search tools, fake HTTP
  workflow.py     Temporal model: activities, retries, signals, replay, nondeterminism check
  tracing.py      Arize: OpenInference-style spans, redaction, safe exporters
  agent.py        the refund agent wiring all four together
  evals.py        golden-set evaluation + reports
  deploy.py       release gate (fails closed)
  cli.py          python -m agentic_stack ...
extensions/live/  opt-in real integrations (Bedrock+Databricks, Temporal worker, Arize/Phoenix bridge)
tests/            contract tests per partner seam (run in CI without secrets)
labs/  docs/  data/golden.jsonl
```

## Going live (optional)

```bash
pip install -e '.[live]'
python extensions/live/live_agent.py            # dry run: prints wiring, checks env
temporal server start-dev                        # then see extensions/live/temporal_worker.py
python extensions/live/arize_bridge.py --target phoenix
```

Details, required env vars, and the exact object you replace for each partner:
[docs/live-providers.md](docs/live-providers.md). Payments always stay fake.

## Honest scope

- `workflow.py` is a teaching model of Temporal's guarantees, not Temporal. The real SDK version
  is `extensions/live/temporal_worker.py` (checked against a local Temporal dev server).
- Fake clients mirror the public request/response shapes of the Bedrock Converse API, the
  Databricks SQL Statement Execution and Vector Search APIs, and OpenInference attribute names.
  Check the vendor docs for your account/workspace before production use.
- This repo is an independent community workshop companion, not official material from AWS,
  Temporal, Arize, or Databricks.

## License

MIT
