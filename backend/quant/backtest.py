"""回测编排：加载数据 → 策略生成目标权重 → 引擎撮合 → 指标、基准对比与诊断。"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from .data.catalog import INDEXES, is_futures
from .data.loader import DataError, data_range, load_bars, load_benchmarks, resolve_universe, symbol_name
from .engine.config import BacktestConfig
from .engine.engine import CORP_ACTIONS, NON_TRADES, EngineOutput, run_engine
from .engine.ledger import Trade
from .engine.metrics import (
    drawdown,
    max_drawdown_info,
    period_returns,
    relative_stats,
    summarize,
)
from .strategies.base import ParamError, Strategy, StrategyOutput, get_strategy_class

MAX_CHART_SYMBOLS = 6  # 价格 + 指标 + 买卖点图最多展示的标的数
REGIME_THRESHOLD = 0.03  # 基准月涨跌幅超过 ±3% 视为上涨 / 下跌月，否则为震荡月


@dataclass
class BacktestResult:
    id: str
    kind: str  # "single" / "portfolio"
    title: str
    strategy: dict[str, Any]
    params: dict[str, Any]
    universe: list[str]
    config: dict[str, Any]
    metrics: dict[str, Any]
    benchmarks: dict[str, dict[str, Any]]
    series: pd.DataFrame  # date 索引：nav, drawdown, exposure, bench_<code>, bench_dd_<code>
    yearly: pd.DataFrame
    monthly: pd.Series
    trades: list[Trade]
    fills: list
    positions: pd.DataFrame
    charts: list[dict[str, Any]]  # 每个标的的价格、指标线与买卖点
    diagnostics: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    elapsed: float = 0.0
    components: list[dict[str, Any]] = field(default_factory=list)  # 组合回测的子策略


def check_universe(cls: type[Strategy], universe: list[str], bars_types: dict[str, str]) -> None:
    bad = [s for s, t in bars_types.items() if t not in cls.asset_types]
    if bad:
        allowed = "、".join({"stock": "A 股", "industry": "申万行业指数", "futures": "商品期货"}[t]
                           for t in sorted(cls.asset_types))
        raise ParamError(f"{cls.name} 只适用于{allowed}，以下标的不适用：{', '.join(bad)}")
    if len(universe) < cls.min_symbols:
        raise ParamError(f"{cls.name} 至少需要 {cls.min_symbols} 个标的，当前只有 {len(universe)} 个")


def run_backtest(
    strategy_id: str,
    params: dict[str, Any] | None = None,
    universe: str | list[str] | None = None,
    config: BacktestConfig | dict[str, Any] | None = None,
    title: str | None = None,
) -> BacktestResult:
    t0 = time.perf_counter()
    cls = get_strategy_class(strategy_id)
    strat = cls(params)
    cfg = config if isinstance(config, BacktestConfig) else BacktestConfig(**(config or {}))
    symbols = cls.expand_universe(resolve_universe(universe or cls.default_universe))
    range_note = check_period(symbols, cfg)
    bars = load_bars(symbols)  # 全部历史（已缓存）；引擎只撮合回测区间内的交易日
    check_universe(cls, symbols, bars.types)

    out: StrategyOutput = strat.generate(bars)
    weights = out.weights.reindex(columns=symbols).fillna(0.0)
    eng = run_engine(weights, bars, cfg, out.rebalance)
    result = _assemble(
        kind="single",
        title=title or cls.name,
        strategy={"id": cls.id, "name": cls.name, "category": cls.category, "style": cls.style},
        params=strat.params.model_dump(),
        symbols=symbols,
        cfg=cfg,
        eng=eng,
        bars=bars,
        out=out,
    )
    if range_note:
        result.warnings.insert(0, range_note)
    result.elapsed = time.perf_counter() - t0
    return result


def check_period(symbols: list[str], cfg: BacktestConfig) -> str | None:
    """回测区间与数据范围不重叠时直接报错；部分超出时返回提示。"""
    ranges = data_range()
    kinds = {"futures" if is_futures(s) else ("industry" if s.startswith("80") else "stock") for s in symbols}
    labels = {"stock": "A 股", "industry": "申万行业", "futures": "商品期货"}
    start = max(ranges[k][0] for k in kinds if k in ranges)
    end = min(ranges[k][1] for k in kinds if k in ranges)
    desc = "；".join(f"{labels[k]} {ranges[k][0]} 至 {ranges[k][1]}" for k in sorted(kinds) if k in ranges)
    if str(cfg.end) < start or str(cfg.start) > end:
        raise DataError(f"回测区间 {cfg.start} 至 {cfg.end} 不在数据范围内（{desc}），请调整区间")
    notes = []
    if str(cfg.start) < start:
        notes.append(f"数据从 {start} 开始，回测实际从这一天开始")
    if str(cfg.end) > end:
        notes.append(f"数据截至 {end}，回测实际在这一天结束")
    return "；".join(notes) or None


def _assemble(kind, title, strategy, params, symbols, cfg, eng: EngineOutput, bars, out) -> BacktestResult:
    daily = eng.daily
    start_equity = cfg.initial_capital
    # 净值序列以回测前一刻（初始资金）为起点，第一天的交易成本也计入
    first = daily.index[0] - pd.Timedelta(days=1)
    nav = pd.concat([pd.Series([1.0], index=[first]), daily["equity"] / start_equity])
    metrics = summarize(nav, eng.trades, cfg.risk_free_rate)
    rets = nav.pct_change().dropna()

    metrics["avg_gross_exposure"] = float(daily["gross_exposure"].mean())
    metrics["annual_turnover"] = float(daily["turnover"].sum() / max(len(daily), 1) * 252)
    total_cost = sum(f.fee + f.slippage for f in eng.fills)
    metrics["total_cost"] = float(total_cost)
    metrics["cost_ratio"] = float(total_cost / start_equity)
    metrics["fill_count"] = sum(1 for f in eng.fills if f.action not in CORP_ACTIONS)
    metrics["dividends"] = float(eng.dividends)
    metrics["final_equity"] = float(daily["equity"].iloc[-1])
    metrics["initial_capital"] = float(start_equity)

    series = pd.DataFrame({"nav": nav, "drawdown": drawdown(nav)})
    series["exposure"] = daily["gross_exposure"].reindex(series.index).fillna(0.0)
    benchmarks: dict[str, dict[str, Any]] = {}
    bench_px = load_benchmarks(cfg.benchmarks, daily.index[0], daily.index[-1])
    yearly = pd.DataFrame({"策略": period_returns(nav, "YE")})
    for code in bench_px.columns:
        px = bench_px[code].reindex(daily.index).ffill().dropna()
        if len(px) < 2:
            continue
        # 基准同样以回测前一交易日收盘为起点
        prev = load_benchmarks([code], daily.index[0] - pd.Timedelta(days=15), daily.index[0])
        base = prev[code].iloc[-2] if len(prev) >= 2 else px.iloc[0]
        bnav = pd.concat([pd.Series([1.0], index=[first]), px / base])
        bm = summarize(bnav, None, cfg.risk_free_rate)
        rel = relative_stats(rets, bnav.pct_change().dropna(), cfg.risk_free_rate)
        name = INDEXES[code].name
        benchmarks[code] = {
            "code": code, "name": name,
            **{k: bm[k] for k in ("total_return", "annual_return", "volatility", "sharpe",
                                  "max_drawdown", "calmar")},
            **rel,
            "excess_annual_return": metrics["annual_return"] - bm["annual_return"],
        }
        series[f"bench_{code}"] = bnav.reindex(series.index).ffill()
        series[f"bench_dd_{code}"] = drawdown(series[f"bench_{code}"])
        yearly[name] = period_returns(bnav, "YE")
    yearly.index = yearly.index.year

    monthly = period_returns(nav, "ME")
    main_bench = next(iter(benchmarks), None)
    diagnostics = _diagnose(nav, monthly, series, main_bench, eng, metrics, bars)
    charts = _charts(symbols, bars, out, eng, daily.index) if bars is not None else []
    if strategy.get("category") == "futures" and main_bench:
        out.notes.append("期货策略与股票指数的对比仅作参考：两者风险来源不同，教学中更应关注收益回撤比。")

    return BacktestResult(
        id=uuid.uuid4().hex[:12],
        kind=kind,
        title=title,
        strategy=strategy,
        params=params,
        universe=symbols,
        config=cfg.model_dump(mode="json"),
        metrics=metrics,
        benchmarks=benchmarks,
        series=series,
        yearly=yearly,
        monthly=monthly,
        trades=eng.trades,
        fills=eng.fills,
        positions=eng.positions,
        charts=charts,
        diagnostics=diagnostics,
        warnings=list(dict.fromkeys(eng.warnings)),
        notes=out.notes,
    )


def _diagnose(nav, monthly, series, bench_code, eng: EngineOutput, metrics, bars) -> dict[str, Any]:
    """给智能体做教学分析用的客观诊断数据。"""
    d: dict[str, Any] = {}
    # 行情分段：按主基准的月涨跌把每个月分成上涨 / 下跌 / 震荡
    if bench_code:
        bm = period_returns(series[f"bench_{bench_code}"].dropna(), "ME")
        df = pd.concat([monthly.rename("s"), bm.rename("b")], axis=1).dropna()
        regime = np.where(df["b"] > REGIME_THRESHOLD, "上涨月",
                          np.where(df["b"] < -REGIME_THRESHOLD, "下跌月", "震荡月"))
        g = df.assign(regime=regime).groupby("regime")
        d["regimes"] = {
            k: {"months": int(len(v)), "strategy_avg_monthly": float(v["s"].mean()),
                "benchmark_avg_monthly": float(v["b"].mean()),
                "strategy_win_months": float((v["s"] > 0).mean())}
            for k, v in g
        }
        d["regime_benchmark"] = INDEXES[bench_code].name
    # 回撤：最大的三段
    d["top_drawdowns"] = _top_drawdowns(nav, 3)
    # 交易层面
    closed = [t for t in eng.trades if not t.is_open]
    if closed:
        pnl = np.array([t.pnl for t in closed])
        streak = cur = 0
        for p in pnl:
            cur = cur + 1 if p <= 0 else 0
            streak = max(streak, cur)
        d["max_consecutive_losses"] = int(streak)
        best = max(closed, key=lambda t: t.pnl)
        worst = min(closed, key=lambda t: t.pnl)
        d["best_trade"] = _trade_brief(best)
        d["worst_trade"] = _trade_brief(worst)
        short_trades = [t for t in closed if t.holding_days <= 3]
        d["short_trade_ratio"] = len(short_trades) / len(closed)
        d["short_trade_win_rate"] = (
            float(np.mean([t.pnl > 0 for t in short_trades])) if short_trades else None
        )
        by_sym: dict[str, float] = {}
        for t in eng.trades:
            by_sym[t.symbol] = by_sym.get(t.symbol, 0.0) + t.pnl
        ranked = sorted(by_sym.items(), key=lambda kv: kv[1], reverse=True)
        d["top_contributors"] = [{"symbol": s, "name": symbol_name(s), "pnl": p} for s, p in ranked[:3]]
        d["bottom_contributors"] = [{"symbol": s, "name": symbol_name(s), "pnl": p}
                                    for s, p in ranked[-3:][::-1] if p < 0]
        if any(t.side == "空" for t in closed):
            d["long_pnl"] = float(sum(t.pnl for t in closed if t.side == "多"))
            d["short_pnl"] = float(sum(t.pnl for t in closed if t.side == "空"))
    d["blocked_orders"] = eng.blocked
    d["cost_drag_annual"] = float(metrics["total_cost"] / metrics["initial_capital"]
                                  / max(metrics["trading_days"], 1) * 252)
    d["time_in_market"] = float((series["exposure"] > 1e-6).mean())
    return d


def _top_drawdowns(nav: pd.Series, k: int) -> list[dict[str, Any]]:
    out = []
    remaining = nav.copy()
    for _ in range(k):
        if len(remaining) < 2:
            break
        info = max_drawdown_info(remaining)
        if info["max_drawdown"] >= -0.01 or info["peak"] is None:
            break
        out.append({
            "drawdown": info["max_drawdown"],
            "peak": str(info["peak"].date()),
            "trough": str(info["trough"].date()),
            "recovery": str(info["recovery"].date()) if info["recovery"] is not None else None,
            "days": info["duration_days"],
        })
        end = info["recovery"] if info["recovery"] is not None else remaining.index[-1]
        remaining = remaining[(remaining.index < info["peak"]) | (remaining.index > end)]
    return out


def _trade_brief(t: Trade) -> dict[str, Any]:
    return {
        "symbol": t.symbol, "name": symbol_name(t.symbol), "side": t.side,
        "entry": str(t.entry_date.date()), "exit": str(t.exit_date.date()) if t.exit_date is not None else None,
        "pnl": t.pnl, "return_pct": t.return_pct, "holding_days": t.holding_days,
    }


def _charts(symbols, bars, out: StrategyOutput, eng: EngineOutput, days) -> list[dict[str, Any]]:
    """为前几个标的准备 K 线、指标线和买卖点，用于"交易点位标记"图。"""
    if not len(eng.fills):
        traded = symbols[:MAX_CHART_SYMBOLS]
    else:
        counts = pd.Series([f.symbol for f in eng.fills if f.action not in NON_TRADES]).value_counts()
        traded = [s for s in counts.index if s in symbols][:MAX_CHART_SYMBOLS] or symbols[:1]
    charts = []
    for s in traded:
        ohlc = pd.DataFrame({
            "open": bars.open[s], "high": bars.high[s], "low": bars.low[s], "close": bars.close[s]
        }).loc[days[0]:days[-1]].dropna()
        lines = {name: df[s].loc[ohlc.index].round(4) for name, df in out.indicators.items()
                 if s in df.columns}
        # 买卖点画在图上时用指标价格体系（股票为前复权价、期货为后复权价），与 K 线一致
        adj = (bars.close[s] / bars.mark_close[s]).reindex(ohlc.index)
        marks = [
            {"date": str(f.date.date()), "action": f.action, "qty": f.qty,
             "price": float(f.price * adj.get(f.date, 1.0)), "raw_price": f.price}
            for f in eng.fills if f.symbol == s and f.action not in NON_TRADES
        ]
        charts.append({"symbol": s, "name": symbol_name(s), "ohlc": ohlc.round(4), "lines": lines,
                       "marks": marks})
    return charts


def trade_to_dict(t: Trade) -> dict[str, Any]:
    d = asdict(t)
    d["name"] = symbol_name(t.symbol)
    d["entry_date"] = str(t.entry_date.date())
    d["exit_date"] = str(t.exit_date.date()) if t.exit_date is not None else None
    return d


__all__ = ["BacktestResult", "run_backtest", "trade_to_dict", "DataError", "ParamError"]
