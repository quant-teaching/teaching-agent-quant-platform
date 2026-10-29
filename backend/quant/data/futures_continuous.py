"""由单个期货合约构建主力连续合约与次主力腿。

为什么不用行情网站现成的"主力连续"：它直接把不同月份合约的价格拼接起来，换月当天会出现
新旧合约价差造成的跳空。拿它算收益，会把这段价差当成真实盈亏，趋势策略还会被跳空误触发信号。

本模块的规则：
1. 用 t-1 日收盘后的持仓量决定 t 日使用哪个合约（不使用未来信息）；
2. 只向更远月份换月，不会换回近月，避免主力来回切换；
3. 次主力腿（代码后缀 .next）取比主力更远的合约中持仓量最大者，供跨期套利使用；
4. 每行保留 pre_close：同一合约的前一日收盘价。当日收益 = close / pre_close - 1，
   换月当天也只计算新合约自身的涨跌，价差不会混入收益；
5. adj_factor 为比例后复权因子（最新一段为 1），用于计算均线、ATR 等技术指标。
   盈亏和下单数量用原始价格计算。
"""

from __future__ import annotations

import pandas as pd

from .catalog import NEXT_LEG_SUFFIX

COLUMNS = ["date", "symbol", "contract", "open", "high", "low", "close", "pre_close",
           "volume", "hold", "roll", "adj_factor"]


def _choose(hold_prev: pd.Series, available: set[str], floor: str | None) -> str | None:
    """在当日有行情、且不早于 floor 的合约中，选前一日持仓量最大的。"""
    cand = hold_prev[[c for c in hold_prev.index if c in available and (floor is None or c >= floor)]]
    cand = cand[cand > 0]
    return None if cand.empty else str(cand.idxmax())


def _build_product(df: pd.DataFrame, product: str) -> pd.DataFrame:
    bars = df.set_index(["date", "contract"]).sort_index()
    hold = df.pivot(index="date", columns="contract", values="hold").sort_index()
    dates = hold.index
    rows_main, rows_next = [], []
    main = nxt = None
    for i in range(1, len(dates)):
        t, prev = dates[i], dates[i - 1]
        available = set(bars.loc[t].index)
        hold_prev = hold.loc[prev].dropna()

        new_main = _choose(hold_prev, available, main)
        if new_main is None:
            continue
        main = new_main
        later = hold_prev[[c for c in hold_prev.index if c > main]]
        new_next = _choose(later, available, nxt if nxt and nxt > main else None)
        nxt = new_next

        for contract, rows in ((main, rows_main), (nxt, rows_next)):
            if contract is None:
                continue
            bar = bars.loc[(t, contract)]
            prev_bar = bars.loc[(prev, contract)] if (prev, contract) in bars.index else None
            if prev_bar is None:
                continue
            rows.append(
                {
                    "date": t, "contract": contract, "open": bar["open"], "high": bar["high"],
                    "low": bar["low"], "close": bar["close"], "pre_close": prev_bar["close"],
                    "volume": bar["volume"], "hold": bar["hold"],
                }
            )

    out = []
    for symbol, rows in ((product, rows_main), (product + NEXT_LEG_SUFFIX, rows_next)):
        if not rows:
            continue
        s = pd.DataFrame(rows)
        s.insert(1, "symbol", symbol)
        s["roll"] = s["contract"].ne(s["contract"].shift()) & s.index.to_series().gt(0)
        # 比例后复权：从最后一天往前，每跨过一次换月就乘上新旧合约的价格比
        ret = s["close"] / s["pre_close"]
        adj_close = ret.cumprod()
        adj_close = adj_close / adj_close.iloc[-1] * s["close"].iloc[-1]
        s["adj_factor"] = adj_close / s["close"]
        out.append(s[COLUMNS])
    return pd.concat(out, ignore_index=True)


def build_continuous(contracts: pd.DataFrame) -> pd.DataFrame:
    """contracts：列为 date, product, contract, open, high, low, close, volume, hold 的长表。"""
    parts = [
        _build_product(g.drop(columns="product"), product)
        for product, g in contracts.groupby("product", sort=True)
    ]
    return pd.concat(parts, ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)
