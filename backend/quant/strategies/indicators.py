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


def bias(close: pd.DataFrame, n: int) -> pd.DataFrame:
    """乖离率 BIAS = 收盘价 / N 日均线 − 1，衡量价格偏离均线的程度"""
    return close / sma(close, n) - 1


def cci(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, n: int) -> pd.DataFrame:
    """顺势指标 CCI = (典型价 − 典型价 N 日均值) / (0.015 × 平均绝对偏差)，典型价 = (高 + 低 + 收) / 3"""
    tp = (high + low + close) / 3
    ma = tp.rolling(n, min_periods=n).mean()
    # 平均绝对偏差：窗口内每个典型价与当日均值之差的绝对值的平均（逐个滞后相加，避免逐窗口循环）
    md = sum((tp.shift(j) - ma).abs() for j in range(n)) / n
    return (tp - ma) / (0.015 * md.replace(0, np.nan))


def williams_r(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, n: int) -> pd.DataFrame:
    """威廉指标 %R = (N 日最高 − 收盘) / (N 日最高 − N 日最低) × (−100)，取值 −100 ~ 0"""
    hh = high.rolling(n, min_periods=n).max()
    ll = low.rolling(n, min_periods=n).min()
    return (hh - close) / (hh - ll).replace(0, np.nan) * -100


def obv(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """能量潮 OBV：收盘上涨日累加成交量、下跌日累减，平盘不变"""
    sign = np.sign(close.diff()).fillna(0)
    return (sign * volume.fillna(0)).cumsum().where(close.notna())


def dmi(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, n: int):
    """趋向指标 DMI（威尔德）：返回 +DI、−DI、ADX。
    +DM = 今高 − 昨高（大于 0 且大于 −DM 时有效），−DM = 昨低 − 今低（同理）；
    ±DI = ±DM 的威尔德平滑 / ATR × 100；DX = |+DI − −DI| / (+DI + −DI) × 100；ADX = DX 的威尔德平滑"""
    up = high.diff()
    down = -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0).where(up.notna())
    minus_dm = down.where((down > up) & (down > 0), 0.0).where(down.notna())
    tr = wilder(true_range(high, low, close), n)
    pdi = 100 * wilder(plus_dm, n) / tr.replace(0, np.nan)
    mdi = 100 * wilder(minus_dm, n) / tr.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return pdi, mdi, wilder(dx, n)


def parabolic_sar(high: pd.DataFrame, low: pd.DataFrame, step: float, max_af: float):
    """抛物线转向指标 SAR（威尔德）。返回 (SAR 值, 方向 1 多 / −1 空)。

    SAR(t+1) = SAR(t) + AF × (EP − SAR(t))，EP 为本轮趋势的极值价，AF 从 step 起每创新极值加 step、最大 max_af；
    多头时 SAR 不高于前两日最低价，价格跌破 SAR 即翻空（空头对称）。
    """
    H, L = high.to_numpy(float), low.to_numpy(float)
    T, K = H.shape
    sar = np.full((T, K), np.nan)
    trend = np.zeros((T, K))
    for k in range(K):
        idx = np.nonzero(~np.isnan(H[:, k]) & ~np.isnan(L[:, k]))[0]
        if len(idx) < 2:
            continue
        h, lo = H[idx, k], L[idx, k]
        s = np.full(len(idx), np.nan)
        d = np.zeros(len(idx))
        up = h[1] >= h[0]
        cur, ep, af = (lo[0], h[1], step) if up else (h[0], lo[1], step)
        for i in range(1, len(idx)):
            if i > 1:
                cur = cur + af * (ep - cur)
                if up:
                    cur = min(cur, lo[i - 1], lo[i - 2])
                else:
                    cur = max(cur, h[i - 1], h[i - 2])
            if up and lo[i] < cur:
                up, cur, ep, af = False, ep, lo[i], step
            elif not up and h[i] > cur:
                up, cur, ep, af = True, ep, h[i], step
            elif up and h[i] > ep:
                ep, af = h[i], min(af + step, max_af)
            elif not up and lo[i] < ep:
                ep, af = lo[i], min(af + step, max_af)
            s[i], d[i] = cur, 1 if up else -1
        sar[idx, k], trend[idx, k] = s, d
    return (pd.DataFrame(sar, index=high.index, columns=high.columns),
            pd.DataFrame(trend, index=high.index, columns=high.columns))


def kama(close: pd.DataFrame, n: int, fast: int, slow: int) -> pd.DataFrame:
    """考夫曼自适应均线 KAMA：效率比 ER = |N 日净变化| / N 日逐日变化绝对值之和，
    平滑系数 SC = (ER × (2/(fast+1) − 2/(slow+1)) + 2/(slow+1))²，KAMA(t) = KAMA(t−1) + SC × (收盘 − KAMA(t−1))"""
    change = (close - close.shift(n)).abs()
    path = close.diff().abs().rolling(n, min_periods=n).sum()
    er = (change / path.replace(0, np.nan)).fillna(0).where(change.notna())
    fsc, ssc = 2 / (fast + 1), 2 / (slow + 1)
    sc = ((er * (fsc - ssc) + ssc) ** 2).to_numpy(float)
    C = close.to_numpy(float)
    out = np.full(C.shape, np.nan)
    prev = np.full(C.shape[1], np.nan)
    for t in range(C.shape[0]):
        ok = ~np.isnan(sc[t]) & ~np.isnan(C[t])
        start = ok & np.isnan(prev)
        prev = np.where(start, C[t], prev)
        upd = ok & ~start
        prev = np.where(upd, prev + sc[t] * (C[t] - prev), prev)
        out[t] = np.where(np.isnan(C[t]), np.nan, prev)
    return pd.DataFrame(out, index=close.index, columns=close.columns)


def rsrs(high: pd.DataFrame, low: pd.DataFrame, n: int):
    """阻力支撑相对强度 RSRS：用最近 N 日最高价对最低价做最小二乘回归，返回 (斜率 β, 拟合优度 R²)。
    β 大说明支撑强于阻力（低点抬升时高点涨得更多），常用于大盘择时"""
    mh = high.rolling(n, min_periods=n).mean()
    ml = low.rolling(n, min_periods=n).mean()
    cov = (high * low).rolling(n, min_periods=n).mean() - mh * ml
    vl = (low * low).rolling(n, min_periods=n).mean() - ml * ml
    vh = (high * high).rolling(n, min_periods=n).mean() - mh * mh
    beta = cov / vl.where(vl > 1e-12)
    r2 = (cov * cov) / (vl * vh).where((vl > 1e-12) & (vh > 1e-12))
    return beta, r2.clip(0, 1)


def trix(close: pd.DataFrame, n: int) -> pd.DataFrame:
    """三重指数平滑 TRIX：TR = EMA(EMA(EMA(收盘, N), N), N)，TRIX = (TR / 昨日 TR − 1) × 100"""
    tr = ema(ema(ema(close, n), n), n)
    return (tr / tr.shift() - 1) * 100
