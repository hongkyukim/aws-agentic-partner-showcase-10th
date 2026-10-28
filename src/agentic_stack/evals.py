"""Offline evaluation harness (Arize-style evals over the golden set)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agent import RefundAgent, build_local_agent
from .models import AgentRequest

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "data" / "golden.jsonl"


def load_golden(path: Path = GOLDEN) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _run_case(agent: RefundAgent, case: dict[str, Any]):
    req = AgentRequest(case["id"], case["customer_id"], case["order_id"], case["message"])
    result = agent.start(req)
    if result.status == "awaiting_approval" and "approval" in case:
        result = agent.signal(result.workflow_id, "approval", case["approval"])
    return result


def evaluate(agent: RefundAgent | None = None, cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    agent = agent or build_local_agent()
    cases = cases if cases is not None else load_golden()
    rows: list[dict[str, Any]] = []
    for case in cases:
        result = _run_case(agent, case)
        decision = result.decision or {"action": result.status, "amount": 0.0, "citations": []}
        history = agent.store.load(result.workflow_id)[1]
        approved_signal = any(e["type"] == "SignalReceived" and e["name"] == "approval" for e in history)
        is_refund = decision["action"] == "refund"
        rows.append(
            {
                "case_id": case["id"],
                "context.trace_id": result.trace_id,
                "expected_action": case["expected_action"],
                "actual_action": decision["action"],
                "eval.correctness.label": "correct" if decision["action"] == case["expected_action"] else "incorrect",
                "eval.correctness.score": 1.0 if decision["action"] == case["expected_action"] else 0.0,
                "amount_ok": abs(decision["amount"] - case.get("expected_amount", 0.0)) < 0.01,
                "grounded": (not is_refund) or bool(decision.get("citations")),
                "approval_ok": (not is_refund) or decision["amount"] <= agent.approval_threshold or approved_signal,
                "explanation": decision.get("reason", ""),
            }
        )
    n = len(rows) or 1
    refunds = [r for r in rows if r["actual_action"] == "refund"]
    return {
        "cases": len(rows),
        "decision_accuracy": round(sum(r["eval.correctness.score"] for r in rows) / n, 3),
        "amount_accuracy": round(sum(r["amount_ok"] for r in rows) / n, 3),
        "groundedness": round(sum(r["grounded"] for r in refunds) / len(refunds), 3) if refunds else 1.0,
        "approval_compliance": round(sum(r["approval_ok"] for r in rows) / n, 3),
        "money_movements": agent.payments.money_movements,
        "telemetry_export_failures": agent.tracer.export_failures,
        "rows": rows,
    }


def write_reports(report: dict[str, Any], out_dir: Path = ROOT / "reports") -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "eval.json"
    md_path = out_dir / "eval.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    lines = [
        "# Evaluation report",
        "",
        f"- cases: {report['cases']}",
        f"- decision_accuracy: {report['decision_accuracy']}",
        f"- amount_accuracy: {report['amount_accuracy']}",
        f"- groundedness: {report['groundedness']}",
        f"- approval_compliance: {report['approval_compliance']}",
        f"- money_movements: {report['money_movements']}",
        "",
        "| case | expected | actual | label |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {r['case_id']} | {r['expected_action']} | {r['actual_action']} | {r['eval.correctness.label']} |"
        for r in report["rows"]
    ]
    md_path.write_text("\n".join(lines) + "\n")
    return json_path, md_path
