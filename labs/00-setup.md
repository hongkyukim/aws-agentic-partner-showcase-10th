# Lab 0 — Setup and the baseline run (10 min)

Prereqs: Python 3.11+, git. Optional: `uv` (for `make test`), `make`.

```bash
git clone https://github.com/hongkyukim/aws-agentic-partner-showcase-10th.git
cd aws-agentic-partner-showcase-10th
make demo
make test
```

No uv? `python3 -m pip install 'pytest>=8,<9' && PYTHONPATH=src python3 -m pytest -q`

## What to notice in `make demo`

1. **Scenario 1**: the trace shows two `payments.refund` spans with `ERROR` followed by `OK`.
   The payment gateway failed twice, the activity retried, and `money movements: ...` still
   counts one refund for that order.
2. **Scenario 2**: status `awaiting_approval`. After the signal, `re-executed=['issue_refund']`.
   The order lookup, retrieval, and LLM call were **not** repeated.
3. **Scenario 3**: customer C-01 asks about C-02's order and gets `order not found`. The SQL
   parameters scope the query to the customer.

## Checkpoint
- [ ] `make demo` prints three scenarios
- [ ] `make test` reports all tests passing
