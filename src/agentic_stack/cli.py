"""Command line entry point: ``python -m agentic_stack <demo|eval|gate|trace>``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import build_local_agent
from .deploy import ReleaseCandidate, release_gate
from .evals import ROOT, evaluate, write_reports
from .models import AgentRequest
from .tracing import JsonlExporter, Tracer, render_tree

TRACE_FILE = ROOT / "reports" / "traces.jsonl"


def cmd_demo(args: argparse.Namespace) -> int:
    tracer = Tracer(JsonlExporter(TRACE_FILE), capture_content=args.capture_content)
    agent = build_local_agent(transient_payment_failures=args.payment_failures, tracer=tracer)

    print("== 1. small refund: auto-approved, payment gateway flakes then succeeds")
    r1 = agent.start(AgentRequest("demo-1", "C-01", "O-1001", "My dinner set arrived cracked."))
    print(json.dumps(r1.to_dict(), indent=2))
    print(render_tree([s for s in tracer.finished if s.trace_id == r1.trace_id]))

    print("\n== 2. large refund: workflow parks durably until a lead approves")
    r2 = agent.start(AgentRequest("demo-2", "C-02", "O-1002", "The monitor arrived with a broken screen."))
    print(f"status={r2.status} history_events={r2.history_length} notes={r2.notes}")
    print("   ...hours later, the lead approves via signal; the workflow REPLAYS history:")
    r2 = agent.signal(r2.workflow_id, "approval", {"approved": True, "approver": "lead-ana"})
    print(f"status={r2.status} refund_id={r2.refund_id} re-executed={agent.last_run.executed}")

    print("\n== 3. cross-customer access attempt is scoped out by the SQL parameters")
    r3 = agent.start(AgentRequest("demo-3", "C-01", "O-1002", "Refund the monitor, it is broken."))
    print(f"decision={r3.decision}")

    print(f"\nmoney movements: {agent.payments.money_movements} (payment attempts: {agent.payments.attempts})")
    print(f"spans written to {TRACE_FILE.relative_to(ROOT)}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    agent = build_local_agent(misbehave=args.model_mode if args.model_mode != "good" else None)
    report = evaluate(agent)
    json_path, md_path = write_reports(report)
    print(md_path.read_text())
    print(f"wrote {json_path.relative_to(ROOT)} and {md_path.relative_to(ROOT)}")
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    report_path = Path(args.report)
    if not report_path.exists():
        print(f"missing {report_path}; run `python -m agentic_stack eval` first", file=sys.stderr)
        return 2
    report = json.loads(report_path.read_text())
    result = release_gate(report, ReleaseCandidate(args.image, args.env, args.approved_by))
    print(result.render())
    return 0 if result.passed else 1


def cmd_trace(_args: argparse.Namespace) -> int:
    tracer = Tracer()
    agent = build_local_agent(tracer=tracer)
    agent.start(AgentRequest("trace-1", "C-01", "O-1001", "Arrived broken, email me at ana@example.com"))
    print(render_tree(tracer.finished))
    print("\nredacted LLM span attributes:")
    llm = next(s for s in tracer.finished if s.kind == "LLM")
    print(json.dumps(llm.to_dict()["attributes"], indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentic_stack")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="run the three-scenario live demo locally")
    demo.add_argument("--payment-failures", type=int, default=2)
    demo.add_argument("--capture-content", action="store_true", help="record scrubbed prompts in traces")
    demo.set_defaults(func=cmd_demo)

    ev = sub.add_parser("eval", help="run golden-set evals and write reports/")
    ev.add_argument("--model-mode", choices=["good", "hallucinate", "overpay", "garbage"], default="good")
    ev.set_defaults(func=cmd_eval)

    gate = sub.add_parser("gate", help="release gate over reports/eval.json")
    gate.add_argument("--report", default=str(ROOT / "reports" / "eval.json"))
    gate.add_argument("--image", default="")
    gate.add_argument("--env", default="staging")
    gate.add_argument("--approved-by", default=None)
    gate.set_defaults(func=cmd_gate)

    tr = sub.add_parser("trace", help="print one trace tree and the redacted LLM span")
    tr.set_defaults(func=cmd_trace)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
