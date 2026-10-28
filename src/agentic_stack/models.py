"""Shared domain types for the refund-exception agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Order:
    order_id: str
    customer_id: str
    item: str
    amount: float
    status: str
    days_since_delivery: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyChunk:
    doc_id: str
    text: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentRequest:
    request_id: str
    customer_id: str
    order_id: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Decision:
    """Validated model output. Anything that fails validation becomes `escalate`."""

    action: str  # refund | deny | escalate
    amount: float
    reason: str
    citations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["citations"] = list(self.citations)
        return data


@dataclass
class AgentResult:
    request_id: str
    workflow_id: str
    status: str  # completed | awaiting_approval
    decision: dict[str, Any] | None = None
    refund_id: str | None = None
    trace_id: str | None = None
    history_length: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
