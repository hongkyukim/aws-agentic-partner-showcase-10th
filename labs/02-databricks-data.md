# Lab 2 — Databricks: governed data tools (15 min)

Files: `src/agentic_stack/databricks.py`, `tests/test_databricks.py`

## Concepts
- The agent never writes SQL. It calls `get_order(order_id, customer_id)`, which sends a fixed
  statement with named markers to `POST /api/2.0/sql/statements`.
- Input validation (`O-\d{4}`) runs **before** any network call, so injection attempts never
  reach the warehouse.
- Retrieval goes through `POST /api/2.0/vector-search/indexes/{index}/query` with bounded
  `num_results`.
- Customer scoping in the `WHERE` clause blocks cross-customer reads (golden case G-06).

## Run
```bash
PYTHONPATH=src python3 -m pytest tests/test_databricks.py -v
```

## Exercises
1. Add a `get_recent_orders(customer_id, limit)` tool. `limit` must be bounded, and the test must
   assert the statement text never contains the customer id.
2. Add a policy doc `POL-DIGITAL` ("digital goods are non-refundable once downloaded") to
   `POLICIES` and a golden case for it. Does retrieval surface it? Adjust the query in
   `agent._retrieve_policies` if not.
3. Production discussion: should customer scoping live in the SQL, in a Unity Catalog row
   filter, or both? What does each protect against?

## Going live
Create the table + index described in `docs/live-providers.md` § Databricks.
