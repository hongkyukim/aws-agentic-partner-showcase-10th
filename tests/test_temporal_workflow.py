import pytest

from agentic_stack.agent import build_local_agent
from agentic_stack.models import AgentRequest
from agentic_stack.workflow import (
    ActivityFailed,
    DurableRun,
    NondeterminismError,
    NonRetryableError,
    RetryPolicy,
    WorkflowBlocked,
)


def test_replay_returns_recorded_results_without_re_executing():
    calls = []

    def side_effect(x):
        calls.append(x)
        return {"value": x * 2}

    run = DurableRun("wf-1")
    assert run.execute_activity("double", side_effect, 21) == {"value": 42}
    replay = DurableRun("wf-1", list(run.history))
    assert replay.execute_activity("double", side_effect, 21) == {"value": 42}
    assert calls == [21]
    assert replay.executed == []


def test_replay_detects_nondeterministic_workflow_code():
    run = DurableRun("wf-1")
    run.execute_activity("a", lambda: 1)
    replay = DurableRun("wf-1", list(run.history))
    with pytest.raises(NondeterminismError):
        replay.execute_activity("b", lambda: 2)


def test_retries_with_backoff_then_succeeds():
    attempts, sleeps = [], []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionError("timeout")
        return "ok"

    run = DurableRun("wf", sleep=sleeps.append)
    assert run.execute_activity("flaky", flaky, retry=RetryPolicy(maximum_attempts=3, initial_interval_s=1)) == "ok"
    assert sleeps == [1, 2]
    assert [e["type"] for e in run.history].count("ActivityAttemptFailed") == 2


def test_non_retryable_error_stops_immediately():
    attempts = []

    def bad():
        attempts.append(1)
        raise NonRetryableError("invalid")

    with pytest.raises(ActivityFailed):
        DurableRun("wf").execute_activity("bad", bad)
    assert len(attempts) == 1


def test_signal_unblocks_workflow():
    run = DurableRun("wf")
    with pytest.raises(WorkflowBlocked):
        run.wait_for_signal("approval")
    run.signal("approval", {"approved": True})
    assert run.wait_for_signal("approval") == {"approved": True}


def test_agent_parks_for_approval_and_resumes_without_repeating_side_effects():
    agent = build_local_agent()
    result = agent.start(AgentRequest("r1", "C-02", "O-1002", "screen arrived broken"))
    assert result.status == "awaiting_approval"
    sql_calls_before = len(agent.data.http.calls)
    llm_calls_before = len(agent.model.client.requests)

    result = agent.signal(result.workflow_id, "approval", {"approved": True, "approver": "lead"})
    assert result.status == "completed" and result.refund_id
    assert agent.last_run.executed == ["issue_refund"]
    assert len(agent.data.http.calls) == sql_calls_before
    assert len(agent.model.client.requests) == llm_calls_before


def test_rejected_approval_moves_no_money():
    agent = build_local_agent()
    r = agent.start(AgentRequest("r2", "C-02", "O-1002", "damaged monitor"))
    r = agent.signal(r.workflow_id, "approval", {"approved": False, "approver": "lead"})
    assert r.decision["action"] == "deny"
    assert agent.payments.money_movements == 0


def test_payment_retries_are_idempotent():
    agent = build_local_agent(transient_payment_failures=2)
    r = agent.start(AgentRequest("r3", "C-01", "O-1001", "arrived cracked"))
    assert r.refund_id
    assert agent.payments.attempts == 3
    assert agent.payments.money_movements == 1
    # a duplicate delivery of the same workflow cannot double-refund
    agent.payments.refund("O-1001", 89.0, "refund-r3:refund")
    assert agent.payments.money_movements == 1
