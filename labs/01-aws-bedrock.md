# Lab 1 — AWS: Bedrock Converse + output guardrails (15 min)

Files: `src/agentic_stack/bedrock.py`, `tests/test_aws_bedrock.py`

## Concepts
- `build_converse_request` produces the Converse API payload (`modelId`, `system`, `messages`,
  `inferenceConfig`) and rejects unbounded `maxTokens`/`temperature`. Cost and latency limits
  belong in code, not just in the console.
- `BedrockConverseModel` only needs an object with `.converse(**req)`, which is the shape of
  `boto3.client("bedrock-runtime")`. That is the whole live swap.
- `parse_decision` treats model output as **untrusted input**. It fails closed to `escalate`.

## Run
```bash
PYTHONPATH=src python3 -m pytest tests/test_aws_bedrock.py -v
PYTHONPATH=src python3 -m agentic_stack eval --model-mode overpay
```
With `overpay`, the model asks for 10x the order value. Read `reports/eval.md`: every refund
became `escalate`, and no money moved.

## Exercises
1. Add a rule: a `deny` must cite at least one policy. Write the failing test first.
2. Add a `--model-mode` that returns a refund for an order in transit. Which existing check
   catches it? If none does, add one.
3. Production discussion: which of these checks could move into Amazon Bedrock Guardrails, and
   which must stay in app code because they need order data?

## Going live
`docs/live-providers.md` § AWS, then `python extensions/live/live_agent.py`.
