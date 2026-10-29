"""量化评价指标。每个函数的注释给出公式，教学文档和智能体解读都以这里为准。

约定：一年按 252 个交易日计；收益率、回撤等比例类指标以小数表示（0.1 = 10%）。
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .ledger import Trade

TRADING_DAYS = 252


def total_return(nav: pd.Series) -> float:
    """总收益率 = 期末净值 / 期初净值 − 1"""
    return float(nav.iloc[-1] / nav.iloc[0] - 1)


def annual_return(nav: pd.Series) -> float:
    """年化收益率 = (期末净值 / 期初净值)^(252 / 交易日数) − 1，即复合年增长率"""
    n = len(nav) - 1
    if n <= 0 or nav.iloc[-1] <= 0:
        return -1.0 if nav.iloc[-1] <= 0 else 0.0
    return float((nav.iloc[-1] / nav.iloc[0]) ** (TRADING_DAYS / n) - 1)


def volatility(returns: pd.Series) -> float:
    """年化波动率 = 日收益率标准差 × √252"""
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=1) * math.sqrt(TRADING_DAYS))


def sharpe_ratio(returns: pd.Series, rf: float = 0.0) -> float:
    """夏普比率 = (日均收益 − 日无风险利率) / 日收益标准差 × √252"""
    sd = returns.std(ddof=1)
    if len(returns) < 2 or not sd > 0:
        return 0.0
    return float((returns.mean() - rf / TRADING_DAYS) / sd * math.sqrt(TRADING_DAYS))


def sortino_ratio(returns: pd.Series, rf: float = 0.0) -> float:
    """索提诺比率：只用下行波动（低于无风险收益的部分）做分母的夏普比率"""
    excess = returns - rf / TRADING_DAYS
    downside = np.sqrt((np.minimum(excess, 0) ** 2).mean())
    if not downside > 0:
        return 0.0
    return float(excess.mean() / downside * math.sqrt(TRADING_DAYS))


def drawdown(nav: pd.Series) -> pd.Series:
    """回撤序列 = 当前净值 / 历史最高净值 − 1（≤ 0）"""
    return nav / nav.cummax() - 1


def max_drawdown_info(nav: pd.Series) -> dict:
    """最大回撤及其发生区间：峰值日、谷底日、恢复日（未恢复则为 None）、持续交易日数"""
    dd = drawdown(nav)
    trough = dd.idxmin()
    mdd = float(dd.loc[trough])
    if mdd == 0:
        return {"max_drawdown": 0.0, "peak": None, "trough": None, "recovery": None,
                "duration_days": 0}
    peak = nav.loc[:trough].idxmax()
    after = nav.loc[trough:]
    rec = after[after >= nav.loc[peak]]
    recovery = rec.index[0] if len(rec) else None
    end = recovery if recovery is not None else nav.index[-1]
    return {
        "max_drawdown": mdd,
        "peak": peak,
        "trough": trough,
        "recovery": recovery,
        "duration_days": int(((nav.index >= peak) & (nav.index <= end)).sum()),
    }


def calmar_ratio(ann: float, mdd: float) -> float:
    """卡玛比率 = 年化收益率 / |最大回撤|"""
    return float(ann / abs(mdd)) if mdd < 0 else 0.0


def trade_stats(trades: list[Trade]) -> dict:
    """基于已平仓交易：
    胜率 = 盈利笔数 / 平仓笔数；盈亏比 = 平均盈利 / |平均亏损|；
    利润因子 = 盈利总额 / |亏损总额|。
    """
    closed = [t for t in trades if not t.is_open]
    wins = [t.pnl for t in closed if t.pnl > 0]
    losses = [t.pnl for t in closed if t.pnl <= 0]
    n = len(closed)
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    return {
        "trade_count": n,
        "open_trade_count": len(trades) - n,
        "win_rate": len(wins) / n if n else 0.0,
        "profit_loss_ratio": avg_win / abs(avg_loss) if avg_loss < 0 else (math.inf if wins else 0.0),
        "profit_factor": sum(wins) / abs(sum(losses)) if losses and sum(losses) < 0 else 0.0,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "avg_holding_days": float(np.mean([t.holding_days for t in closed])) if closed else 0.0,
        "long_count": sum(1 for t in closed if t.side == "多"),
        "short_count": sum(1 for t in closed if t.side == "空"),
    }


def relative_stats(returns: pd.Series, bench: pd.Series, rf: float = 0.0) -> dict:
    """相对基准：
    β = Cov(策略, 基准) / Var(基准)；
    α（年化）= (策略日均超额收益 − β × 基准日均超额收益) × 252；
    信息比率 = 日超额收益均值 / 日超额收益标准差 × √252；跟踪误差 = 日超额收益标准差 × √252。
    """
    df = pd.concat([returns, bench], axis=1, join="inner").dropna()
    if len(df) < 20:
        return {}
    r, b = df.iloc[:, 0], df.iloc[:, 1]
    var_b = b.var(ddof=1)
    beta = float(r.cov(b) / var_b) if var_b > 0 else 0.0
    d = rf / TRADING_DAYS
    alpha = float(((r - d).mean() - beta * (b - d).mean()) * TRADING_DAYS)
    active = r - b
    te = float(active.std(ddof=1) * math.sqrt(TRADING_DAYS))
    ir = float(active.mean() / active.std(ddof=1) * math.sqrt(TRADING_DAYS)) if te > 0 else 0.0
    return {"beta": beta, "alpha": alpha, "information_ratio": ir, "tracking_error": te,
            "correlation": float(r.corr(b))}


def period_returns(nav: pd.Series, freq: str) -> pd.Series:
    """分期收益率：freq='YE' 为年度，'ME' 为月度。首期以回测起点净值为基数。"""
    ends = nav.resample(freq).last().dropna()
    starts = ends.shift(1)
    starts.iloc[0] = nav.iloc[0]
    return ends / starts - 1


def summarize(nav: pd.Series, trades: list[Trade], rf: float = 0.0) -> dict:
    """全套指标。nav 第一个值为回测起点净值。"""
    rets = nav.pct_change().dropna()
    ann = annual_return(nav)
    mdd = max_drawdown_info(nav)
    out = {
        "total_return": total_return(nav),
        "annual_return": ann,
        "volatility": volatility(rets),
        "sharpe": sharpe_ratio(rets, rf),
        "sortino": sortino_ratio(rets, rf),
        "max_drawdown": mdd["max_drawdown"],
        "calmar": calmar_ratio(ann, mdd["max_drawdown"]),
        "max_drawdown_peak": mdd["peak"],
        "max_drawdown_trough": mdd["trough"],
        "max_drawdown_recovery": mdd["recovery"],
        "max_drawdown_days": mdd["duration_days"],
        "trading_days": len(nav) - 1,
        "best_day": float(rets.max()) if len(rets) else 0.0,
        "worst_day": float(rets.min()) if len(rets) else 0.0,
        "positive_days_ratio": float((rets > 0).mean()) if len(rets) else 0.0,
    }
    if trades is not None:
        out.update(trade_stats(trades))
    return out


METRIC_LABELS = {
    "total_return": "总收益率",
    "annual_return": "年化收益率",
    "max_drawdown": "最大回撤",
    "sharpe": "夏普比率",
    "calmar": "卡玛比率",
    "volatility": "年化波动率",
    "win_rate": "胜率",
    "profit_loss_ratio": "盈亏比",
    "trade_count": "交易次数",
    "sortino": "索提诺比率",
    "profit_factor": "利润因子",
    "avg_holding_days": "平均持仓天数",
    "max_drawdown_days": "最大回撤持续天数",
    "alpha": "阿尔法（年化）",
    "beta": "贝塔",
    "information_ratio": "信息比率",
    "excess_annual_return": "年化超额收益",
}
