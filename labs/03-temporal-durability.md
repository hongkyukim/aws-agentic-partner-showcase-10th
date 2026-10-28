# Lab 3 — Temporal: durable agent workflows (20 min)

Files: `src/agentic_stack/workflow.py`, `agent.py::_workflow`, `tests/test_temporal_workflow.py`,
`extensions/live/temporal_worker.py`

## Concepts
| Temporal idea | Local model | Why agents need it |
|---|---|---|
| Activity | `run.execute_activity(name, fn, ...)` | LLM calls, DB reads, and payments are non-deterministic side effects |
| Event history + replay | `DurableRun(history)` | A crashed worker resumes without re-calling the LLM or re-charging |
| Retry policy | `RetryPolicy(maximum_attempts, backoff)` | Flaky gateways and model throttling |
| Non-retryable error | `NonRetryableError` | Don't retry invalid input |
| Signal | `wait_for_signal("approval")` | Human approval that can take days |
| Nondeterminism check | `NondeterminismError` | Changing workflow code under in-flight runs is dangerous |

Idempotency is the partner of retries: `issue_refund` uses the key `<workflow_id>:refund`.

## Run
```bash
PYTHONPATH=src python3 -m pytest tests/test_temporal_workflow.py -v
make demo   # scenario 2
```

## Exercises
1. Add an approval **timeout**: if no signal arrives, escalate. (Hint: a `timer` event, or
   model it as a second signal `approval_timeout` sent by a scheduler.)
2. Reorder two activities in `_workflow`, then replay an old history. Watch
   `NondeterminismError`. How does real Temporal handle this (`workflow.patched`, worker
   versioning)?
3. Remove the idempotency key (use a random key) and write the test that proves duplicates now
   happen.

## Real Temporal
```bash
pip install -e '.[live]'
temporal server start-dev                                   # UI: http://localhost:8233
PYTHONPATH=src python extensions/live/temporal_worker.py worker
PYTHONPATH=src python extensions/live/temporal_worker.py start --id refund-live-2 \
  --customer C-02 --order O-1002 --message "The monitor arrived with a broken screen."
# kill and restart the worker now; the workflow keeps waiting
PYTHONPATH=src python extensions/live/temporal_worker.py approve --id refund-live-2 --approver lead-ana
```
In the UI, find the `ActivityTaskFailed` retry for the injected payment failure, and the
`WorkflowExecutionSignaled` event.
