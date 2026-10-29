import math

import numpy as np
import pandas as pd
import pytest

from quant.engine.config import BacktestConfig, stamp_duty_rate
from quant.engine.engine import run_engine
from quant.engine.metrics import annual_return, max_drawdown_info, sharpe_ratio, summarize
from tests.helpers import make_bars

CAP = 1_000_000


def cfg(bars, **kw):
    d = bars.dates
    base = dict(start=d[0].date(), end=d[-1].date(), initial_capital=CAP, benchmarks=[])
    base.update(kw)
    return BacktestConfig(**base)


def test_signal_executes_next_open_no_lookahead():
    bars = make_bars({"600519": [100, 101, 102, 103, 104]})
    w = pd.DataFrame({"600519": [0, 0, 1, 1, 1]}, index=bars.dates, dtype=float)
    out = run_engine(w, bars, cfg(bars, stock_slippage=0))
    # 第 3 天收盘出信号，第 4 天开盘（= 第 3 天收盘 102）买入
    assert out.fills[0].date == bars.dates[3]
    assert out.fills[0].price == pytest.approx(102)


def test_stock_lot_size_commission_and_stamp_duty():
    bars = make_bars({"600519": [100, 100, 110, 110]})
    w = pd.DataFrame({"600519": [1, 1, 0, 0]}, index=bars.dates, dtype=float)
    c = cfg(bars, stock_slippage=0, stock_commission=0.0003, stock_min_commission=5)
    out = run_engine(w, bars, c)
    buy, sell = out.fills
    # 100 万按 100 元买入：受佣金影响买不满 10000 股，按 100 股一手向下取整
    assert buy.qty % 100 == 0 and buy.qty == 9900
    assert buy.fee == pytest.approx(9900 * 100 * 0.0003)
    expected_sell_fee = 9900 * 110 * 0.0003 + 9900 * 110 * stamp_duty_rate(bars.dates[2].date())
    assert sell.fee == pytest.approx(expected_sell_fee)
    final = CAP - 9900 * 100 - buy.fee + 9900 * 110 - sell.fee
    assert out.daily["equity"].iloc[-1] == pytest.approx(final)
    t = out.trades[0]
    assert t.pnl == pytest.approx(9900 * 10 - buy.fee - sell.fee)


def test_stamp_duty_halved_after_2023_08_28():
    from datetime import date
    assert stamp_duty_rate(date(2023, 8, 25)) == 0.001
    assert stamp_duty_rate(date(2023, 8, 28)) == 0.0005


def test_limit_up_open_blocks_buy_until_next_day():
    # 第 2 天开盘即涨停（+10%），买单顺延到第 3 天
    bars = make_bars({"600036": [10, 10, 11, 11.5, 11.5]},
                     opens={"600036": [10, 10, 11, 11.2, 11.5]})
    w = pd.DataFrame({"600036": [1, 1, 1, 1, 1]}, index=bars.dates, dtype=float)
    w.iloc[0] = 0
    out = run_engine(w, bars, cfg(bars, stock_slippage=0))
    assert out.blocked == 1
    assert out.fills[0].date == bars.dates[3]


def test_futures_mark_to_market_and_short():
    # 螺纹钢乘数 10；做空 1 手，价格从 3500 跌到 3400 应盈利 1000 元（未计成本）
    prices = [3500, 3500, 3450, 3400]
    bars = make_bars({"RB": prices})
    target = -3500 * 10 / CAP  # 恰好 1 手的名义权重
    w = pd.DataFrame({"RB": [target * 1.01] * 4}, index=bars.dates)
    c = cfg(bars, futures_slippage_ticks=0, futures_commission_scale=0)
    out = run_engine(w, bars, c)
    assert out.fills[0].qty == -1
    assert out.daily["equity"].iloc[-1] == pytest.approx(CAP + 1000)


def test_futures_roll_pnl_ignores_contract_gap():
    # 第 3 天换月：旧合约收 3500，新合约前一日收 3600（远月升水 100）。
    # 新合约当日收 3610，真实盈亏应只有 +10/吨，而不是把 110 的跳空算成收益。
    bars = make_bars(
        {"RB": [3500, 3500, 3500, 3610]},
        opens={"RB": [3500, 3500, 3500, 3600]},
        contracts={"RB": ["RB2405", "RB2405", "RB2405", "RB2410"]},
        pre_close={"RB": [np.nan, 3500, 3500, 3600]},
    )
    w = pd.DataFrame({"RB": [3500 * 10 * 2 / CAP] * 4}, index=bars.dates)
    c = cfg(bars, futures_slippage_ticks=0, futures_commission_scale=0)
    out = run_engine(w, bars, c)
    assert out.fills[0].qty == 2
    assert any(f.action == "移仓" for f in out.fills)
    assert out.daily["equity"].iloc[-1] == pytest.approx(CAP + 2 * 10 * 10)


def test_futures_roll_charges_costs():
    bars = make_bars(
        {"RB": [3500, 3500, 3500, 3600]},
        opens={"RB": [3500, 3500, 3500, 3600]},
        contracts={"RB": ["RB2405", "RB2405", "RB2405", "RB2410"]},
        pre_close={"RB": [np.nan, 3500, 3500, 3600]},
    )
    w = pd.DataFrame({"RB": [3500 * 10 * 1.5 / CAP] * 4}, index=bars.dates)
    c = cfg(bars, futures_slippage_ticks=1, futures_commission_scale=0)
    out = run_engine(w, bars, c)
    roll = [f for f in out.fills if f.action == "移仓"][0]
    # 1 手、乘数 10、最小变动 1 元、两条腿各 1 跳
    assert roll.slippage == pytest.approx(1 * 10 * 1 * 2)


def test_margin_cap_scales_down_futures():
    bars = make_bars({"RB": [3500] * 4})
    w = pd.DataFrame({"RB": [20.0] * 4}, index=bars.dates)  # 20 倍名义杠杆
    out = run_engine(w, bars, cfg(bars, max_margin_ratio=0.5))
    lots = out.fills[0].qty
    assert lots * 3500 * 10 * 0.10 <= 0.5 * CAP + 1e-6


def test_negative_stock_weight_clipped():
    bars = make_bars({"600519": [100, 100, 100]})
    w = pd.DataFrame({"600519": [-1.0] * 3}, index=bars.dates)
    out = run_engine(w, bars, cfg(bars))
    assert not out.fills
    assert any("做空" in m for m in out.warnings)


def test_metrics_formulas():
    idx = pd.bdate_range("2024-01-01", periods=253)
    nav = pd.Series(np.linspace(1, 1.2, 253), index=idx)
    assert annual_return(nav) == pytest.approx(0.2, rel=1e-9)  # 恰好 252 个收益日
    dd_nav = pd.Series([1, 1.2, 0.9, 1.0, 1.3], index=idx[:5])
    info = max_drawdown_info(dd_nav)
    assert info["max_drawdown"] == pytest.approx(0.9 / 1.2 - 1)
    assert info["peak"] == idx[1] and info["trough"] == idx[2] and info["recovery"] == idx[4]
    r = pd.Series([0.01, -0.005, 0.02, 0.0, -0.01])
    assert sharpe_ratio(r) == pytest.approx(r.mean() / r.std(ddof=1) * math.sqrt(252))


def test_round_trip_win_rate():
    bars = make_bars({"600519": [100, 100, 110, 110, 110, 90, 90]})
    w = pd.DataFrame({"600519": [1, 1, 0, 1, 0, 0, 0]}, index=bars.dates, dtype=float)
    out = run_engine(w, bars, cfg(bars, stock_slippage=0))
    m = summarize(out.daily["equity"] / CAP, out.trades)
    assert m["trade_count"] == 2
    assert m["win_rate"] == pytest.approx(0.5)
