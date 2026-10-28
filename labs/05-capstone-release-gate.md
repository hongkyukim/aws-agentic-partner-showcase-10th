# Lab 5 — Capstone: release gate to AWS (15 min)

Files: `src/agentic_stack/deploy.py`, `tests/test_evals_and_gate.py`, `.github/workflows/ci.yml`

## The gate
`release_gate(report, candidate)` fails closed unless all of these hold:
- `decision_accuracy >= 0.85`, `groundedness == 1.0`, `approval_compliance == 1.0`
- zero telemetry export failures during evals
- the image is pinned by digest (`...@sha256:<64 hex>`), not a mutable tag
- environment is `dev|staging|prod`; `prod` needs a named approver

## Run
```bash
make eval && make gate                        # PASS
PYTHONPATH=src python3 -m agentic_stack gate --env prod \
  --image "123456789012.dkr.ecr.us-west-2.amazonaws.com/refund-agent:latest"   # FAIL x2
make eval-bad && make gate                    # FAIL on accuracy
```

## Capstone flow (end to end)
1. Change something real: a policy, the approval threshold, or a prompt in `bedrock.py`.
2. `make test eval gate`. If the gate fails, fix the agent, not the threshold.
3. Push. CI runs the same gate (see `.github/workflows/ci.yml`).
4. Deploy (discussion): build the container, push to ECR, deploy the **digest** to Amazon
   Bedrock AgentCore Runtime or ECS/Fargate; run Temporal workers alongside; export OTel to
   Arize; Databricks access through a service principal with least-privilege grants.

## Discussion
- What should trigger a rollback in production, and which Arize monitor would catch it first?
- Who is the approver for prod, and how is that recorded?
- What changes when the eval set grows from 7 to 7,000 cases?
