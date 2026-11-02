"""测试用的手工行情构造。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.data.loader import Bars


def make_bars(
    prices: dict[str, list[float]],
    start: str = "2024-01-02",
    opens: dict[str, list[float]] | None = None,
    contracts: dict[str, list[str]] | None = None,
    pre_close: dict[str, list[float]] | None = None,
    extra: dict[str, dict[str, list[float]]] | None = None,
) -> Bars:
    """prices 为收盘价；开盘价默认等于前一日收盘价（首日等于当日收盘）。"""
    n = len(next(iter(prices.values())))
    idx = pd.bdate_range(start, periods=n, name="date")
    close = pd.DataFrame(prices, index=idx, dtype=float)
    if opens is None:
        op = close.shift().fillna(close)
    else:
        op = pd.DataFrame(opens, index=idx, dtype=float)
    types = {s: ("futures" if s.isalpha() else "stock") for s in prices}
    contract = pd.DataFrame({s: (contracts or {}).get(s, [s] * n) for s in prices}, index=idx)
    roll = contract.ne(contract.shift()) & np.arange(n)[:, None].astype(bool)
    pre = pd.DataFrame(pre_close, index=idx, dtype=float) if pre_close else close.shift()
    return Bars(
        symbols=list(prices),
        types=types,
        open=op, high=np.maximum(op, close), low=np.minimum(op, close), close=close,
        volume=close * 0 + 1e6,
        exec_open=op, mark_close=close, mark_pre_close=pre,
        tradable=close.notna(), roll=roll, contract=contract,
        extra={k: pd.DataFrame(v, index=idx, dtype=float) for k, v in (extra or {}).items()},
    )
