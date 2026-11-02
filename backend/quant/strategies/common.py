"""策略公共工具：状态机、止盈止损、调仓日、截面选股、网格仓位。"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import Field

from .base import StrategyParams


class StopParams(StrategyParams):
    """止盈止损（择时类策略通用）。按收盘价判断，触发后次日开盘离场，直到原始信号重新开仓。"""

    stop_loss: float = Field(0.0, ge=0, le=0.5, title="止损比例",
                             description="相对开仓信号日收盘价亏损达到该比例时离场，0 表示不启用")
    take_profit: float = Field(0.0, ge=0, le=5, title="止盈比例",
                               description="相对开仓信号日收盘价盈利达到该比例时离场，0 表示不启用")


def state_machine(
    entry_long: pd.DataFrame,
    exit_long: pd.DataFrame,
    entry_short: pd.DataFrame | None = None,
    exit_short: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """把进出场条件变成持仓状态（1 多 / 0 空仓 / −1 空）。同一天既有离场又有反向进场时直接反手。"""
    el = entry_long.fillna(False).to_numpy(bool)
    xl = exit_long.fillna(False).to_numpy(bool)
    es = entry_short.fillna(False).to_numpy(bool) if entry_short is not None else np.zeros_like(el)
    xs = exit_short.fillna(False).to_numpy(bool) if exit_short is not None else np.zeros_like(el)
    pos = np.zeros(el.shape)
    cur = np.zeros(el.shape[1])
    for i in range(el.shape[0]):
        cur = np.where((cur > 0) & xl[i], 0, cur)
        cur = np.where((cur < 0) & xs[i], 0, cur)
        cur = np.where((cur <= 0) & el[i], 1, cur)
        cur = np.where((cur >= 0) & es[i] & ~el[i], -1, cur)
        pos[i] = cur
    return pd.DataFrame(pos, index=entry_long.index, columns=entry_long.columns)


def apply_stops(position: pd.DataFrame, close: pd.DataFrame, stop_loss: float,
                take_profit: float) -> pd.DataFrame:
    """在持仓状态上叠加止盈止损。触发后保持空仓，直到原始信号变化（重新开仓或反向）。"""
    if stop_loss <= 0 and take_profit <= 0:
        return position
    raw = position.to_numpy(float)
    px = close.to_numpy(float)
    out = raw.copy()
    entry = np.full(raw.shape[1], np.nan)
    locked = np.zeros(raw.shape[1], bool)
    prev = np.zeros(raw.shape[1])
    for i in range(raw.shape[0]):
        changed = raw[i] != prev
        locked &= ~changed
        new_entry = changed & (raw[i] != 0)
        entry = np.where(new_entry, px[i], entry)
        entry = np.where(raw[i] == 0, np.nan, entry)
        side = np.sign(raw[i])
        pnl = side * (px[i] / entry - 1)
        hit = np.zeros_like(locked)
        if stop_loss > 0:
            hit |= pnl <= -stop_loss
        if take_profit > 0:
            hit |= pnl >= take_profit
        locked |= hit & (raw[i] != 0)
        out[i] = np.where(locked, 0, raw[i])
        prev = raw[i]
    return pd.DataFrame(out, index=position.index, columns=position.columns)


def rebalance_mask(index: pd.DatetimeIndex, freq: str) -> pd.Series:
    """每个周期最后一个交易日为 True。freq：W 周、M 月、Q 季。信号在该日收盘生成、次日开盘调仓。"""
    key = {"W": index.to_period("W"), "M": index.to_period("M"), "Q": index.to_period("Q")}[freq]
    s = pd.Series(key, index=index)
    return s.ne(s.shift(-1))


def top_k_weights(score: pd.DataFrame, k: int, mask: pd.Series, total: float = 1.0,
                  ascending: bool = False) -> pd.DataFrame:
    """在调仓日按分数选出前 k 名等权持有（total 为总仓位），非调仓日沿用上次结果。"""
    vals = score.to_numpy(float)
    out = np.full(vals.shape, np.nan)
    for i in np.nonzero(mask.reindex(score.index).fillna(False).to_numpy(bool))[0]:
        row = vals[i]
        ok = np.nonzero(~np.isnan(row))[0]
        if not len(ok):
            continue
        chosen = ok[_order(row[ok], ascending)[:k]]
        out[i] = 0.0
        out[i, chosen] = total / len(chosen)
    return pd.DataFrame(out, index=score.index, columns=score.columns).ffill().fillna(0.0)


def _order(v: np.ndarray, ascending: bool) -> np.ndarray:
    """与 pandas Series.sort_values 相同的排序（含并列时的先后），保证选股结果不因实现方式改变。"""
    if ascending:
        return v.argsort(kind="quicksort")
    idx = np.arange(len(v))[::-1]
    return idx[v[::-1].argsort(kind="quicksort")][::-1]


def weighted_on_mask(raw: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    """只在调仓日采用 raw 中的权重，其余日期沿用。"""
    m = mask.reindex(raw.index).fillna(False).astype(bool)
    return raw.fillna(0.0).where(m, axis=0).ffill().fillna(0.0)


def grid_position(close: pd.DataFrame, base: pd.DataFrame, step: float, levels: int,
                  allow_short: bool) -> pd.DataFrame:
    """网格仓位：价格相对基准价每下跌一格加一档多仓，每上涨一格减一档（期货可继续做空）。

    返回 −1~1 的仓位比例。为避免价格在格线附近来回抖动导致频繁交易，
    只有越过下一条格线才调整档位（滞回）。
    """
    dev = (close / base - 1).to_numpy(float)
    out = np.zeros(dev.shape)
    level = np.zeros(dev.shape[1])
    lo = -levels if allow_short else 0
    for i in range(dev.shape[0]):
        d = dev[i]
        target = np.clip(np.where(np.isnan(d), 0, -d / step), -levels, levels)
        # 价格每跌过一格才加一档，涨过一格才减一档
        up = target >= level + 1
        down = target <= level - 1
        level = np.where(up, np.floor(target), level)
        level = np.where(down, np.ceil(target), level)
        level = np.clip(level, lo, levels)
        level = np.where(np.isnan(d), 0, level)
        out[i] = level / levels
    return pd.DataFrame(out, index=close.index, columns=close.columns)


def pool_weights(position: pd.DataFrame, ratio: float) -> pd.DataFrame:
    """择时策略用于股票池时：每只股票分得 ratio / N 的资金槽位，信号为 1 时满槽持有。"""
    return position.clip(lower=0) * (ratio / position.shape[1])
