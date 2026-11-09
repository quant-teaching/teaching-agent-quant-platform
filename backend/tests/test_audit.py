"""独立核验：不经过回测引擎，用原始行情和成交记录重算成交价、手续费与期末权益。"""

import pytest
from fastapi.testclient import TestClient

from agent.agent import fact_check
from api.main import app

PERIOD = {"start": "2019-01-01", "end": "2024-12-31"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("sid", ["dual_ma_stock", "dividend_rotation", "grid_stock", "industry_rotation"])
def test_stock_backtest_reconciles_to_the_cent(client, sid):
    rid = client.post("/api/backtests", json={"strategy": sid, "config": PERIOD}).json()["id"]
    a = client.get(f"/api/backtests/{rid}/audit").json()
    assert a["supported"] and a["checks"] and all(c["ok"] for c in a["checks"]), a["checks"]
    r = a["reconcile"]
    assert abs(r["diff"]) < 0.01 and r["computed"] == pytest.approx(r["reported"])
    row = a["rows"][0]
    assert row["open"] == round(row["open"], 2), "开盘价按分报价，可直接与行情软件对照"


def test_dividends_are_part_of_the_ledger(client):
    rid = client.post("/api/backtests", json={"strategy": "dividend_rotation", "config": PERIOD}).json()["id"]
    assert client.get(f"/api/backtests/{rid}/audit").json()["reconcile"]["dividends"] > 0


def test_futures_fill_prices_match_contract_open(client):
    rid = client.post("/api/backtests", json={"strategy": "turtle_futures", "config": {"start": "2021-01-01", "end": "2023-12-31"}}).json()["id"]
    a = client.get(f"/api/backtests/{rid}/audit").json()
    assert a["reconcile"] is None and all(c["ok"] for c in a["checks"])
    assert a["rows"][0]["contract"] and a["rows"][0]["open"] is not None


def test_portfolio_is_explained_not_audited(client):
    rid = client.post("/api/backtests/portfolio", json={"components": [{"strategy": "dual_ma_stock"}, {"strategy": "momentum_stock"}],
                                                         "config": PERIOD}).json()["id"]
    a = client.get(f"/api/backtests/{rid}/audit").json()
    assert not a["supported"] and "子策略" in a["reason"]


def test_fact_check_reports_where_each_number_came_from():
    r = fact_check("年化 12.3%，夏普 0.72，另一个 9.99", [{"_src": "工具结果「执行回测」", "data": {"metrics": {"年化收益率": "12.3%", "夏普比率": "0.72"}}}])
    assert r["status"] == "warn" and r["unmatched"] == ["9.99"]
    assert [m["source"] for m in r["matches"]] == ["工具结果「执行回测」 · metrics · 年化收益率：12.3%",
                                                   "工具结果「执行回测」 · metrics · 夏普比率：0.72"]
