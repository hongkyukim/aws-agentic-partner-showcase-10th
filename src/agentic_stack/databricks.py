"""Databricks seam: governed data tools for the agent.

Two tools, both behind an injected ``HttpCaller(method, path, body) -> dict``:

* SQL Statement Execution API (``POST /api/2.0/sql/statements``) with *named
  parameter markers* - the agent never string-formats SQL.
* Vector Search index query (``POST /api/2.0/vector-search/indexes/{name}/query``).

``FakeDatabricksHttp`` serves in-memory data with the same response shapes.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from .models import Order, PolicyChunk

HttpCaller = Callable[[str, str, dict[str, Any]], dict[str, Any]]

ORDER_ID_PATTERN = re.compile(r"^O-\d{4}$")
ORDER_SQL = (
    "SELECT order_id, customer_id, item, amount, status, days_since_delivery "
    "FROM main.support.orders WHERE order_id = :order_id AND customer_id = :customer_id"
)


def build_statement_request(warehouse_id: str, statement: str, parameters: dict[str, Any]) -> dict[str, Any]:
    if not warehouse_id:
        raise ValueError("warehouse_id is required")
    if ";" in statement:
        raise ValueError("multiple statements are not allowed")
    for name in parameters:
        if f":{name}" not in statement:
            raise ValueError(f"parameter {name!r} has no :{name} marker in statement")
    markers = set(re.findall(r":([a-zA-Z_]\w*)", statement))
    missing = markers - set(parameters)
    if missing:
        raise ValueError(f"statement markers without values: {sorted(missing)}")
    return {
        "warehouse_id": warehouse_id,
        "statement": statement,
        "parameters": [{"name": k, "value": str(v), "type": "STRING"} for k, v in parameters.items()],
        "wait_timeout": "30s",
        "disposition": "INLINE",
        "format": "JSON_ARRAY",
    }


def _rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    state = response.get("status", {}).get("state")
    if state != "SUCCEEDED":
        raise RuntimeError(f"statement did not succeed: {state}")
    columns = [c["name"] for c in response["manifest"]["schema"]["columns"]]
    return [dict(zip(columns, row)) for row in response.get("result", {}).get("data_array", []) or []]


class DatabricksTools:
    def __init__(self, http: HttpCaller, *, warehouse_id: str, vector_index: str):
        self.http = http
        self.warehouse_id = warehouse_id
        self.vector_index = vector_index

    def get_order(self, order_id: str, customer_id: str) -> Order | None:
        if not ORDER_ID_PATTERN.match(order_id):
            raise ValueError(f"invalid order id: {order_id!r}")
        body = build_statement_request(
            self.warehouse_id, ORDER_SQL, {"order_id": order_id, "customer_id": customer_id}
        )
        rows = _rows(self.http("POST", "/api/2.0/sql/statements", body))
        if not rows:
            return None
        r = rows[0]
        return Order(
            order_id=r["order_id"],
            customer_id=r["customer_id"],
            item=r["item"],
            amount=float(r["amount"]),
            status=r["status"],
            days_since_delivery=int(r["days_since_delivery"]),
        )

    def search_policies(self, query: str, k: int = 3) -> list[PolicyChunk]:
        if not 1 <= k <= 10:
            raise ValueError("k must be in [1, 10]")
        body = {"query_text": query, "columns": ["doc_id", "text"], "num_results": k}
        response = self.http("POST", f"/api/2.0/vector-search/indexes/{self.vector_index}/query", body)
        columns = [c["name"] for c in response["manifest"]["columns"]]
        chunks = []
        for row in response.get("result", {}).get("data_array", []) or []:
            rec = dict(zip(columns, row))
            chunks.append(PolicyChunk(rec["doc_id"], rec["text"], float(rec["score"])))
        return chunks


ORDERS = [
    ("O-1001", "C-01", "ceramic dinner set", 89.00, "delivered", 3),
    ("O-1002", "C-02", "4K monitor", 649.00, "delivered", 5),
    ("O-1003", "C-03", "running shoes", 120.00, "delivered", 45),
    ("O-1004", "C-04", "espresso machine", 410.00, "in_transit", 0),
    ("O-1005", "C-05", "desk lamp", 39.00, "delivered", 10),
]

POLICIES = {
    "POL-DAMAGE": "Items that arrive damaged, broken, or defective qualify for a full refund within 30 days of delivery.",
    "POL-WINDOW": "Refund requests more than 30 days after delivery are not eligible except where required by law.",
    "POL-APPROVAL": "Refunds above $250 require approval from a support lead before money moves.",
    "POL-TRANSIT": "Orders still in transit cannot be refunded; open a carrier investigation instead.",
}


class FakeDatabricksHttp:
    """In-memory Databricks: answers by bound parameters, never by parsing user text."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def __call__(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, path, body))
        if path == "/api/2.0/sql/statements":
            params = {p["name"]: p["value"] for p in body["parameters"]}
            rows = [
                list(row)
                for row in ORDERS
                if row[0] == params.get("order_id") and row[1] == params.get("customer_id")
            ]
            cols = ["order_id", "customer_id", "item", "amount", "status", "days_since_delivery"]
            return {
                "statement_id": f"stmt-{len(self.calls)}",
                "status": {"state": "SUCCEEDED"},
                "manifest": {"schema": {"columns": [{"name": c} for c in cols]}},
                "result": {"data_array": rows},
            }
        if path.startswith("/api/2.0/vector-search/indexes/") and path.endswith("/query"):
            terms = set(re.findall(r"[a-z]+", body["query_text"].lower()))
            scored = []
            for doc_id, text in POLICIES.items():
                overlap = len(terms & set(re.findall(r"[a-z]+", text.lower())))
                scored.append([doc_id, text, round(overlap / (len(terms) or 1), 3)])
            scored.sort(key=lambda r: (-r[2], r[0]))
            return {
                "manifest": {"columns": [{"name": "doc_id"}, {"name": "text"}, {"name": "score"}]},
                "result": {"data_array": scored[: body["num_results"]]},
            }
        raise ValueError(f"unexpected Databricks call {method} {path}")
