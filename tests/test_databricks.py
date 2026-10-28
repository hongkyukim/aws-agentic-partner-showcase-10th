import pytest

from agentic_stack.databricks import ORDER_SQL, DatabricksTools, FakeDatabricksHttp, build_statement_request


def tools():
    http = FakeDatabricksHttp()
    return DatabricksTools(http, warehouse_id="wh-1", vector_index="main.support.policy_index"), http


def test_statement_uses_named_parameters_not_string_formatting():
    t, http = tools()
    t.get_order("O-1001", "C-01")
    method, path, body = http.calls[0]
    assert (method, path) == ("POST", "/api/2.0/sql/statements")
    assert "O-1001" not in body["statement"]
    assert body["statement"] == ORDER_SQL
    assert {"name": "order_id", "value": "O-1001", "type": "STRING"} in body["parameters"]
    assert body["warehouse_id"] == "wh-1"


@pytest.mark.parametrize("bad", ["O-1001' OR '1'='1", "1001", "O-1001; DROP TABLE x"])
def test_order_id_is_validated_before_any_call(bad):
    t, http = tools()
    with pytest.raises(ValueError):
        t.get_order(bad, "C-01")
    assert http.calls == []


def test_statement_builder_rejects_multi_statements_and_unbound_markers():
    with pytest.raises(ValueError):
        build_statement_request("wh", "SELECT 1; SELECT 2", {})
    with pytest.raises(ValueError):
        build_statement_request("wh", "SELECT * FROM t WHERE a = :a", {})
    with pytest.raises(ValueError):
        build_statement_request("wh", "SELECT 1", {"a": 1})


def test_orders_are_scoped_to_the_customer():
    t, _ = tools()
    assert t.get_order("O-1002", "C-02") is not None
    assert t.get_order("O-1002", "C-01") is None


def test_vector_search_request_and_parsing():
    t, http = tools()
    chunks = t.search_policies("item arrived damaged refund 30 days delivery", k=3)
    _, path, body = http.calls[-1]
    assert path == "/api/2.0/vector-search/indexes/main.support.policy_index/query"
    assert body["num_results"] == 3 and body["columns"] == ["doc_id", "text"]
    assert chunks[0].doc_id == "POL-DAMAGE"
    assert len(chunks) == 3


def test_vector_search_k_is_bounded():
    t, _ = tools()
    with pytest.raises(ValueError):
        t.search_policies("x", k=50)
