from agentic_stack.agent import build_local_agent
from agentic_stack.cli import main
from agentic_stack.deploy import ReleaseCandidate, release_gate
from agentic_stack.evals import evaluate, load_golden

PINNED = "123456789012.dkr.ecr.us-west-2.amazonaws.com/refund-agent@sha256:" + "a" * 64


def test_golden_set_passes_with_good_model():
    report = evaluate(build_local_agent())
    assert report["cases"] == len(load_golden())
    assert report["decision_accuracy"] == 1.0
    assert report["groundedness"] == 1.0
    assert report["approval_compliance"] == 1.0


def test_misbehaving_model_moves_no_money_and_fails_the_gate():
    for mode in ("hallucinate", "overpay", "garbage"):
        agent = build_local_agent(misbehave=mode)
        report = evaluate(agent)
        assert agent.payments.money_movements == 0, mode
        assert not release_gate(report, ReleaseCandidate(PINNED, "staging")).passed, mode


def test_gate_requires_pinned_image_and_prod_approver():
    report = evaluate(build_local_agent())
    assert release_gate(report, ReleaseCandidate(PINNED, "staging")).passed
    assert not release_gate(report, ReleaseCandidate("refund-agent:latest", "staging")).passed
    assert not release_gate(report, ReleaseCandidate(PINNED, "prod")).passed
    assert release_gate(report, ReleaseCandidate(PINNED, "prod", approved_by="release-mgr")).passed
    assert not release_gate(report, ReleaseCandidate(PINNED, "qa")).passed


def test_cli_demo_and_trace_run(capsys):
    assert main(["trace"]) == 0
    assert "[LLM] bedrock.converse" in capsys.readouterr().out
