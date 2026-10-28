# Lab 4 — Arize: tracing and evals (20 min)

Files: `src/agentic_stack/tracing.py`, `evals.py`, `tests/test_arize_tracing.py`,
`extensions/live/arize_bridge.py`

## Concepts
- One trace per request; span kinds follow OpenInference: `AGENT`, `TOOL`, `RETRIEVER`, `LLM`,
  `GUARDRAIL`.
- Attribute names are the contract with the backend: `input.value`, `output.value`,
  `llm.model_name`, `llm.token_count.*`, `tool.name`, `retrieval.documents.N.document.id`.
- Content is `[REDACTED]` by default. With `--capture-content`, emails and card numbers are still
  scrubbed.
- Exporter failures are counted (`export_failures`) and never raised.
- Evals produce Arize-style columns (`eval.correctness.label/score`) joined on `context.trace_id`.

## Run
```bash
make trace
PYTHONPATH=src python3 -m agentic_stack demo --capture-content && head -c 600 reports/traces.jsonl
make eval && make eval-bad && cat reports/eval.md
PYTHONPATH=src python3 -m pytest tests/test_arize_tracing.py -v
```

## Exercises
1. Add a `tool_call_accuracy` eval: for refunds, was `issue_refund` called exactly once?
   (Hint: count `payments.refund` spans with status OK per trace.)
2. Add a latency budget: fail the eval if any LLM span is over N ms. Where would you set N for
   Bedrock in production?
3. Production discussion: which span attributes are safe as metric labels? (Not trace ids,
   order ids, or prompts. Keep cardinality bounded.)

## Live
```bash
pip install -e '.[live]'
phoenix serve   # or set ARIZE_SPACE_ID / ARIZE_API_KEY and use --target arize
PYTHONPATH=src python extensions/live/arize_bridge.py --target phoenix
```
