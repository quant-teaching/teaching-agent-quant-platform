"""用真实行情快照检验全部策略：能运行、输出合理、没有未来函数、边界情况给出清晰报错。"""

import math

import numpy as np
import pandas as pd
import pytest

from quant.backtest import run_backtest
from quant.data.loader import DataError, load_bars, resolve_universe
from quant.engine.engine import CORP_ACTIONS
from quant.portfolio.portfolio import Component, PortfolioSpec, run_portfolio
from quant.strategies.base import ParamError, load_all

ALL = sorted(load_all())
PERIOD = {"start": "2021-01-01", "end": "2024-12-31"}


@pytest.mark.parametrize("sid", ALL)
def test_strategy_runs_with_sane_output(sid):
    r = run_backtest(sid, {}, None, PERIOD)
    m = r.metrics
    for k in ("total_return", "annual_return", "max_drawdown", "sharpe", "calmar", "volatility"):
        assert math.isfinite(m[k]), k
    assert -1 < m["max_drawdown"] <= 0
    assert r.series["nav"].gt(0).all()
    assert r.series["nav"].iloc[0] == 1.0
    assert m["fill_count"] > 0, "默认参数下应当有交易"
    # 股票不能做空：持仓数量非负
    stock = [s for s in r.universe if s.isdigit()]
    if stock and not r.positions.empty:
        assert (r.positions[r.positions["symbol"].isin(stock)]["qty"] >= 0).all()
    # 交易记录完整：每笔成交都有正的价格和非负的费用
    assert all(f.price > 0 and f.fee >= 0 and f.slippage >= 0 for f in r.fills if f.action not in CORP_ACTIONS)


@pytest.mark.parametrize("sid", ALL)
def test_no_lookahead(sid):
    """截断数据后，截止日及以前的目标权重必须和用全部数据时完全一致。"""
    cls = load_all()[sid]
    symbols = cls.expand_universe(resolve_universe(cls.default_universe))
    cut = "2023-06-30"
    full = cls().generate(load_bars(symbols)).weights
    part = cls().generate(load_bars(symbols, end=cut)).weights
    a = full.loc[:cut].fillna(0.0)
    b = part.reindex(a.index).fillna(0.0)
    np.testing.assert_allclose(a.to_numpy(), b.to_numpy(), atol=1e-9,
                               err_msg=f"{sid} 的信号用到了 {cut} 之后的数据")


def test_custom_universe_single_stock():
    r = run_backtest("macd_stock", {}, "600519", PERIOD)
    assert r.universe == ["600519"]
    assert r.metrics["fill_count"] > 0


def test_universe_with_next_leg_expands():
    r = run_backtest("calendar_spread_futures", {}, "RB", PERIOD)
    assert r.universe == ["RB", "RB.next"]


def test_wrong_asset_type_rejected():
    with pytest.raises(ParamError, match="只适用于"):
        run_backtest("turtle_futures", {}, "stock_pool", PERIOD)


def test_min_symbols_enforced():
    with pytest.raises(ParamError, match="至少需要"):
        run_backtest("momentum_stock", {}, "600519", PERIOD)


def test_unknown_symbol_rejected():
    with pytest.raises(DataError, match="未知标的"):
        run_backtest("dual_ma_stock", {}, "999999", PERIOD)


def test_period_outside_data_rejected():
    with pytest.raises(DataError, match="不在数据范围内"):
        run_backtest("dual_ma_stock", {}, None, {"start": "2010-01-01", "end": "2010-06-30"})


def test_end_before_start_rejected():
    with pytest.raises(ValueError, match="结束日期必须晚于开始日期"):
        run_backtest("dual_ma_stock", {}, None, {"start": "2024-01-01", "end": "2023-01-01"})


def test_invalid_params_give_chinese_message():
    with pytest.raises(ParamError, match="短均线周期必须小于长均线周期"):
        run_backtest("dual_ma_stock", {"fast": 60, "slow": 30}, None, PERIOD)
    with pytest.raises(ParamError, match="没有名为 foo 的参数"):
        run_backtest("dual_ma_stock", {"foo": 1}, None, PERIOD)
    with pytest.raises(ParamError, match="不能小于"):
        run_backtest("turtle_futures", {"atr_period": 1}, None, PERIOD)


def test_short_period_works():
    r = run_backtest("dual_ma_stock", {}, None, {"start": "2024-03-01", "end": "2024-03-15"})
    assert r.metrics["trading_days"] >= 5


def test_futures_before_continuous_start():
    """期货连续合约从 2020 年开始：完全早于数据时报错，部分早于时给出提示并照常回测。"""
    with pytest.raises(DataError, match="商品期货 2020-01-02"):
        run_backtest("turtle_futures", {}, None, {"start": "2018-01-01", "end": "2019-06-30"})
    r = run_backtest("turtle_futures", {}, None, {"start": "2019-01-01", "end": "2021-06-30"})
    assert "回测实际从这一天开始" in r.warnings[0]


def test_stops_reduce_exposure():
    base = run_backtest("dual_ma_stock", {}, None, PERIOD)
    stop = run_backtest("dual_ma_stock", {"stop_loss": 0.03}, None, PERIOD)
    assert stop.metrics["avg_gross_exposure"] < base.metrics["avg_gross_exposure"]


def test_position_limit_scales_drawdown():
    lo = run_backtest("turtle_futures", {"position_limit": 0.1}, None, PERIOD)
    hi = run_backtest("turtle_futures", {"position_limit": 0.2}, None, PERIOD)
    assert lo.metrics["volatility"] < hi.metrics["volatility"]


def test_portfolio_equal_and_custom_weights():
    spec = PortfolioSpec(components=[Component(strategy_id="dividend_rotation"),
                                     Component(strategy_id="trend_cta_futures")], rebalance="M")
    res, subs = run_portfolio(spec, PERIOD)
    div = res.diagnostics["diversification"]
    assert len(subs) == 2
    assert abs(sum(div["risk_contribution"]) - 1) < 1e-6
    assert div["portfolio_vol"] <= div["weighted_avg_vol"] + 1e-9  # 组合波动不超过加权平均
    # 每日再平衡近似时，组合日收益 = 子策略日收益按权重加总（月度再平衡则在月内漂移）
    spec2 = PortfolioSpec(components=[Component(strategy_id="dividend_rotation", weight=3),
                                      Component(strategy_id="trend_cta_futures", weight=1)], rebalance="none")
    res2, _ = run_portfolio(spec2, PERIOD)
    assert res2.params["weights"] == {"股息率轮动": 0.75, "趋势跟踪 CTA": 0.25}


def test_portfolio_without_rebalance_matches_value_sum():
    """不调仓时，组合净值 = Σ 权重 × 子策略净值。"""
    spec = PortfolioSpec(components=[Component(strategy_id="dual_ma_stock", weight=1),
                                     Component(strategy_id="momentum_stock", weight=1)], rebalance="none")
    res, subs = run_portfolio(spec, PERIOD)
    expect = 0.5 * subs[0].series["nav"] + 0.5 * subs[1].series["nav"]
    got = res.series["nav"].reindex(expect.index)
    np.testing.assert_allclose(got.to_numpy(), expect.to_numpy(), rtol=1e-9)


def test_benchmarks_start_at_one():
    r = run_backtest("dual_ma_stock", {}, None, PERIOD)
    for code in ("000300", "000905", "399006"):
        assert r.series[f"bench_{code}"].iloc[0] == pytest.approx(1.0)
    # 沪深 300 的总收益与指数收盘价直接计算一致
    from quant.data.loader import read_dataset
    px = read_dataset("index_daily")
    px = px[px["symbol"] == "000300"].set_index("date")["close"]
    px.index = pd.to_datetime(px.index)
    before = px[px.index < "2021-01-01"].iloc[-1]
    last = px[px.index <= "2024-12-31"].iloc[-1]
    assert r.benchmarks["000300"]["total_return"] == pytest.approx(last / before - 1, rel=1e-9)
