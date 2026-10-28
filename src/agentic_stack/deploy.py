"""AWS deployment seam: a release gate that must pass before an agent version ships.

The gate consumes the eval report plus a release candidate description and fails closed.
Wire it into CodePipeline / GitHub Actions before deploying to Amazon Bedrock AgentCore
Runtime, ECS/Fargate, or Lambda (see labs/05-capstone-release-gate.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

DIGEST = re.compile(r"^[\w.\-/:]+@sha256:[0-9a-f]{64}$")
ENVIRONMENTS = ("dev", "staging", "prod")


@dataclass(frozen=True)
class Thresholds:
    decision_accuracy: float = 0.85
    groundedness: float = 1.0
    approval_compliance: float = 1.0
    max_export_failures: int = 0


@dataclass(frozen=True)
class ReleaseCandidate:
    image_uri: str
    environment: str
    approved_by: str | None = None


@dataclass
class GateResult:
    passed: bool
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"release gate: {'PASS' if self.passed else 'FAIL'}"]
        lines += [f"  [{'ok' if ok else 'XX'}] {name}: {detail}" for name, ok, detail in self.checks]
        return "\n".join(lines)


def release_gate(report: dict[str, Any], candidate: ReleaseCandidate, thresholds: Thresholds = Thresholds()) -> GateResult:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append((name, ok, detail))

    for metric in ("decision_accuracy", "groundedness", "approval_compliance"):
        value = float(report.get(metric, 0.0))
        floor = getattr(thresholds, metric)
        check(metric, value >= floor, f"{value} >= {floor}")
    failures = int(report.get("telemetry_export_failures", 0))
    check("telemetry", failures <= thresholds.max_export_failures, f"{failures} export failures")
    check("image_pinned", bool(DIGEST.match(candidate.image_uri)), candidate.image_uri or "<missing>")
    check("environment", candidate.environment in ENVIRONMENTS, candidate.environment)
    if candidate.environment == "prod":
        check("prod_approval", bool(candidate.approved_by), candidate.approved_by or "no approver")
    return GateResult(all(ok for _, ok, _ in checks), checks)
