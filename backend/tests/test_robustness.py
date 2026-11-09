"""参数稳健性检验（样本内 / 样本外、参数高原）。"""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from quant import robustness as rb
from quant.backtest import run_backtest
from quant.strategies.base import ParamError


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_grid_segments_match_a_direct_backtest():
    out = rb.run("dual_ma_stock", {}, None, "2021-01-01", "2024-12-31", "fast", [5, 10], "slow", [30, 60],
                 split="2023-01-01")
    assert out["count"] == 4 and out["backtests"] == 5 and out["split"] == "2023-01-01"
    cell = next(c for c in out["cells"] if c["x"] == 5 and c["y"] == 60)
    nav = run_backtest("dual_ma_stock", {"fast": 5, "slow": 60}, None, {"start": "2021-01-01", "end": "2024-12-31"}
                       ).series["nav"].iloc[1:]
    test = nav[nav.index >= "2023-01-01"]
    assert cell["test"]["total_return"] == pytest.approx(test.iloc[-1] / test.iloc[0] - 1)  # 样本外从分割日重新计净值
    ranks = sorted(c["test_rank"] for c in [out["best_train"], out["robust"]])
    assert all(1 <= r <= 4 for r in ranks)
    assert -1 <= out["spearman"] <= 1 and out["conclusions"]


def test_invalid_combinations_are_skipped_not_fatal():
    out = rb.run("dual_ma_stock", {}, None, "2021-01-01", "2024-12-31", "fast", [10, 40], "slow", [30, 60])
    bad = [c for c in out["cells"] if not c["ok"]]
    assert len(bad) == 1 and "短均线" in bad[0]["error"]  # fast=40 ≥ slow=30 不合法
    assert out["count"] == 3


@pytest.mark.parametrize("kw, msg", [
    ({"x_key": "nope", "x_values": [1, 2]}, "没有参数"),
    ({"x_key": "fast", "x_values": [5]}, "至少要给 2 个取值"),
    ({"x_key": "fast", "x_values": list(range(2, 9)), "y_key": "slow", "y_values": list(range(30, 37))}, "最多"),
    ({"x_key": "fast", "x_values": [5, 10], "split": "2030-01-01"}, "分割日"),
])
def test_bad_requests_give_chinese_errors(kw, msg):
    with pytest.raises(ParamError, match=msg):
        rb.run("dual_ma_stock", {}, None, "2021-01-01", "2024-12-31", **kw)


def test_api_endpoint(client):
    r = client.post("/api/research/robustness", json={"strategy": "海龟", "start": "2021-01-01", "end": "2024-12-31",
                                                      "x_key": "entry_window", "x_values": [20, 40, 55]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["strategy"]["id"] == "turtle_futures" and d["y"] is None and len(d["cells"]) == 3
    bad = client.post("/api/research/robustness", json={"strategy": "海龟", "start": "2021-01-01", "end": "2024-12-31",
                                                        "x_key": "atr_period", "x_values": [1, 2]})
    assert bad.status_code == 400 and "有效的参数组合不足" in bad.json()["detail"]
