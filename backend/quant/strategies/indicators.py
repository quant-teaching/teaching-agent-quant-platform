"""技术指标。输入输出都是"日期 × 标的"的宽表，逐列独立计算，只使用当前及过去的数据。"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(x: pd.DataFrame, n: int) -> pd.DataFrame:
    """简单移动平均"""
    return x.rolling(n, min_periods=n).mean()


def ema(x: pd.DataFrame, n: int) -> pd.DataFrame:
    """指数移动平均，平滑系数 α = 2 / (n + 1)"""
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def wilder(x: pd.DataFrame, n: int) -> pd.DataFrame:
    """威尔德平滑，α = 1 / n，用于 ATR、RSI"""
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def true_range(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    """真实波幅 TR = max(最高 − 最低, |最高 − 昨收|, |最低 − 昨收|)"""
    pc = close.shift()
    return np.maximum(high - low, np.maximum((high - pc).abs(), (low - pc).abs()))


def atr(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, n: int) -> pd.DataFrame:
    """平均真实波幅 ATR：TR 的威尔德平滑"""
    return wilder(true_range(high, low, close), n)


def rsi(close: pd.DataFrame, n: int) -> pd.DataFrame:
    """相对强弱指数 RSI = 100 − 100 / (1 + 平均涨幅 / 平均跌幅)"""
    d = close.diff()
    up = wilder(d.clip(lower=0), n)
    down = wilder((-d).clip(lower=0), n)
    rs = up / down.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(down != 0, 100.0).where(up.notna())


def macd(close: pd.DataFrame, fast: int, slow: int, signal: int):
    """MACD：DIF = EMA(fast) − EMA(slow)，DEA = EMA(DIF, signal)，柱 = 2 × (DIF − DEA)"""
    dif = ema(close, fast) - ema(close, slow)
    dea = dif.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return dif, dea, 2 * (dif - dea)


def kdj(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, n: int, m1: int, m2: int):
    """KDJ：RSV = (收盘 − N 日最低) / (N 日最高 − N 日最低) × 100，
    K = RSV 的 m1 日平滑，D = K 的 m2 日平滑，J = 3K − 2D（国内常用 9,3,3）"""
    ll = low.rolling(n, min_periods=n).min()
    hh = high.rolling(n, min_periods=n).max()
    rsv = (close - ll) / (hh - ll).replace(0, np.nan) * 100
    rsv = rsv.fillna(50).where(ll.notna())
    k = rsv.ewm(alpha=1 / m1, adjust=False).mean()
    d = k.ewm(alpha=1 / m2, adjust=False).mean()
    return k, d, 3 * k - 2 * d


def bollinger(close: pd.DataFrame, n: int, k: float):
    """布林带：中轨 = N 日均线，上下轨 = 中轨 ± k × N 日标准差"""
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return mid, mid + k * sd, mid - k * sd


def donchian(high: pd.DataFrame, low: pd.DataFrame, n: int):
    """唐奇安通道：过去 N 日（不含当日）的最高价与最低价"""
    return high.rolling(n, min_periods=n).max().shift(), low.rolling(n, min_periods=n).min().shift()


def zscore(x: pd.DataFrame, n: int) -> pd.DataFrame:
    """滚动 Z 分数 = (x − N 日均值) / N 日标准差"""
    m = x.rolling(n, min_periods=n).mean()
    s = x.rolling(n, min_periods=n).std(ddof=0)
    return (x - m) / s.replace(0, np.nan)


def momentum(close: pd.DataFrame, lookback: int, skip: int = 0) -> pd.DataFrame:
    """动量 = 过去 lookback 日的涨幅，跳过最近 skip 日（剔除短期反转效应）"""
    return close.shift(skip) / close.shift(lookback) - 1


def realized_vol(close: pd.DataFrame, n: int) -> pd.DataFrame:
    """N 日已实现年化波动率"""
    return close.pct_change().rolling(n, min_periods=max(5, n // 2)).std() * np.sqrt(252)


def cross_up(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """a 上穿 b"""
    return (a > b) & (a.shift() <= b.shift())


def cross_down(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """a 下穿 b"""
    return (a < b) & (a.shift() >= b.shift())


def cs_zscore(x: pd.DataFrame) -> pd.DataFrame:
    """截面标准化：每天在所有标的之间做 Z 分数"""
    m = x.mean(axis=1)
    s = x.std(axis=1, ddof=0).replace(0, np.nan)
    return x.sub(m, axis=0).div(s, axis=0)
