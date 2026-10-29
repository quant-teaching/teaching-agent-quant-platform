"""多策略组合回测与分散化分析。

做法：每个子策略先用全部初始资金独立回测，得到各自的日收益率；再按权重把资金分给各子策略，
每天各子账户按自己的收益增长（权重会随表现漂移），到调仓日再把资金重新按目标权重分配。
这相当于假设子策略的收益与资金规模成正比（忽略整手取整的影响），是组合分析的标准近似。
"""

from __future__ import annotations

import time
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator

from ..backtest import BacktestResult, _assemble, run_backtest
from ..engine.config import BacktestConfig
from ..engine.engine import EngineOutput
from ..strategies.base import ParamError, StrategyOutput
from ..strategies.common import rebalance_mask


class Component(BaseModel):
    strategy_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    universe: str | list[str] | None = None
    weight: float | None = Field(None, ge=0, description="自定义权重；全部为空时等权")
    label: str | None = None


class PortfolioSpec(BaseModel):
    components: list[Component] = Field(min_length=2, max_length=8)
    rebalance: Literal["none", "M", "Q"] = Field("M", description="none 不调仓，M 每月、Q 每季度调回目标权重")

    @model_validator(mode="after")
    def _check(self):
        ws = [c.weight for c in self.components]
        if any(w is not None for w in ws) and any(w is None for w in ws):
            raise ValueError("要么全部指定权重，要么全部不指定（等权）")
        if all(w is not None for w in ws) and sum(ws) <= 0:
            raise ValueError("权重之和必须大于 0")
        return self

    def normalized_weights(self) -> list[float]:
        ws = [c.weight for c in self.components]
        if all(w is None for w in ws):
            return [1 / len(ws)] * len(ws)
        total = sum(ws)
        return [w / total for w in ws]


def combine_navs(rets: pd.DataFrame, weights: np.ndarray, mask: pd.Series | None) -> pd.DataFrame:
    """按目标权重合成，返回每个子账户的资金曲线（列与 rets 相同），合计即组合净值。"""
    values = np.zeros(rets.shape)
    cur = weights.astype(float).copy()
    r = rets.fillna(0.0).to_numpy()
    m = mask.reindex(rets.index).fillna(False).to_numpy(bool) if mask is not None else None
    for i in range(len(r)):
        cur = cur * (1 + r[i])
        values[i] = cur
        if m is not None and m[i]:
            cur = cur.sum() * weights
    return pd.DataFrame(values, index=rets.index, columns=rets.columns)


def diversification(rets: pd.DataFrame, port: pd.Series, weights: np.ndarray, labels: list[str]) -> dict:
    """分散化分析：
    - 相关系数矩阵：子策略日收益两两相关性，越低分散效果越好；
    - 分散化比率 = Σ(wᵢσᵢ) / σ组合，等于 1 表示没有分散效果，越大越好；
    - 风险贡献 = wᵢ × Cov(rᵢ, r组合) / Var(r组合)，各项之和为 1。
    """
    df = rets.dropna()
    vol = df.std(ddof=1) * np.sqrt(252)
    pv = port.reindex(df.index).std(ddof=1) * np.sqrt(252)
    corr = df.corr()
    var_p = port.reindex(df.index).var(ddof=1)
    rc = [float(weights[i] * df.iloc[:, i].cov(port.reindex(df.index)) / var_p) if var_p > 0 else 0.0
          for i in range(df.shape[1])]
    k = len(labels)
    off = corr.to_numpy()[~np.eye(k, dtype=bool)]
    return {
        "labels": labels,
        "correlation": corr.round(4).to_numpy().tolist(),
        "avg_correlation": float(off.mean()) if off.size else 0.0,
        "component_vol": [float(v) for v in vol],
        "weighted_avg_vol": float((weights * vol.to_numpy()).sum()),
        "portfolio_vol": float(pv),
        "diversification_ratio": float((weights * vol.to_numpy()).sum() / pv) if pv > 0 else 1.0,
        "risk_contribution": rc,
    }


def run_portfolio(spec: PortfolioSpec | dict, config: BacktestConfig | dict, title: str | None = None
                  ) -> tuple[BacktestResult, list[BacktestResult]]:
    t0 = time.perf_counter()
    spec = spec if isinstance(spec, PortfolioSpec) else PortfolioSpec(**spec)
    cfg = config if isinstance(config, BacktestConfig) else BacktestConfig(**config)
    weights = np.array(spec.normalized_weights())
    subs: list[BacktestResult] = []
    for c in spec.components:
        try:
            subs.append(run_backtest(c.strategy_id, c.params, c.universe, cfg, title=c.label))
        except ParamError as e:
            raise ParamError(f"子策略 {c.label or c.strategy_id}：{e}") from e
    labels = []
    for c, s in zip(spec.components, subs):
        lb = c.label or s.strategy["name"]
        while lb in labels:
            lb += "'"
        labels.append(lb)

    # 各子策略日收益（第一行是起点，收益为 0）
    navs = pd.concat([s.series["nav"].rename(lb) for s, lb in zip(subs, labels)], axis=1).ffill()
    rets = navs.pct_change().fillna(0.0)
    mask = None if spec.rebalance == "none" else rebalance_mask(rets.index, spec.rebalance)
    values = combine_navs(rets.iloc[1:], weights, mask)
    nav = pd.concat([pd.Series([1.0], index=navs.index[:1]), values.sum(axis=1)])
    port_ret = nav.pct_change().dropna()

    cap = cfg.initial_capital
    # 拼出一个"组合版"的引擎输出：权益、敞口按资金占比加权
    share = values.div(values.sum(axis=1), axis=0)
    exp = pd.concat([s.series["exposure"].rename(lb) for s, lb in zip(subs, labels)], axis=1).reindex(values.index)
    daily = pd.DataFrame({
        "equity": nav.iloc[1:] * cap,
        "cash": np.nan,
        "market_value": np.nan,
        "gross_exposure": (share * exp.fillna(0)).sum(axis=1),
        "net_exposure": np.nan,
        "margin": np.nan,
        "turnover": 0.0,
    })
    fills, trades = [], []
    for s, lb in zip(subs, labels):
        for f in s.fills:
            f.note = f"[{lb}] {f.note}".strip()
        fills.extend(s.fills)
        trades.extend(s.trades)
    # 组合层面的成本与交易按资金占比折算（子策略在全额资金下回测）
    eng = EngineOutput(daily=daily, positions=pd.DataFrame(), fills=[], trades=trades,
                       warnings=[w for s in subs for w in s.warnings])
    result = _assemble(
        kind="portfolio",
        title=title or " + ".join(labels),
        strategy={"id": "portfolio", "name": "多策略组合", "category": "mixed", "style": "组合"},
        params={"rebalance": spec.rebalance, "weights": dict(zip(labels, weights.round(4).tolist()))},
        symbols=sorted({u for s in subs for u in s.universe}),
        cfg=cfg, eng=eng, bars=None, out=StrategyOutput(weights=pd.DataFrame()),
    )
    result.metrics["total_cost"] = float(sum(s.metrics["total_cost"] * w for s, w in zip(subs, weights)))
    result.metrics["cost_ratio"] = result.metrics["total_cost"] / cap
    result.metrics["fill_count"] = sum(s.metrics["fill_count"] for s in subs)
    result.metrics["annual_turnover"] = float(sum(s.metrics["annual_turnover"] * w for s, w in zip(subs, weights)))
    result.diagnostics["cost_drag_annual"] = float(
        result.metrics["cost_ratio"] / max(result.metrics["trading_days"], 1) * 252)
    result.fills = fills
    for lb, s in zip(labels, subs):
        result.series[f"comp_{lb}"] = s.series["nav"].reindex(result.series.index).ffill()
        result.yearly[lb] = s.yearly["策略"]
    div = diversification(rets.iloc[1:], port_ret, weights, labels)
    result.diagnostics["diversification"] = div
    best_single_mdd = max(s.metrics["max_drawdown"] for s in subs)
    result.diagnostics["drawdown_vs_components"] = {
        "portfolio": result.metrics["max_drawdown"],
        "components": {lb: s.metrics["max_drawdown"] for lb, s in zip(labels, subs)},
        "better_than_best_single": result.metrics["max_drawdown"] > best_single_mdd,
    }
    result.components = [
        {"label": lb, "strategy_id": s.strategy["id"], "name": s.strategy["name"], "weight": float(w),
         "result_id": s.id, "params": s.params,
         "metrics": {k: s.metrics[k] for k in ("total_return", "annual_return", "max_drawdown", "sharpe",
                                                "calmar", "volatility", "win_rate", "trade_count")}}
        for lb, s, w in zip(labels, subs, weights)
    ]
    result.notes.append("组合按子策略的日收益率加权合成，假设子策略收益与资金规模成正比。")
    result.elapsed = time.perf_counter() - t0
    return result, subs
