"""行情加载：把股票、行业指数、期货统一成"日期 × 标的"的宽表。

两套价格：
- open / high / low / close：用于计算技术指标。股票为前复权价，期货为比例后复权价，
  这样分红除权、期货换月都不会在指标里制造假突破。
- exec_open / mark_close / mark_pre_close：用于成交和盯市。股票直接用前复权价
  （含分红再投资效果）；期货用当日实际交易合约的原始价格，盈亏 = 手数 × 乘数 × 原始价差。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache, lru_cache
from typing import Literal

import pandas as pd

from ..paths import MARKET_DIR
from .catalog import FUTURES_SPECS, NEXT_LEG_SUFFIX, STOCKS, is_futures

AssetType = Literal["stock", "industry", "futures"]


class DataError(ValueError):
    """数据缺失或标的不存在。消息面向学习者，可以直接展示。"""


@cache
def read_dataset(name: str) -> pd.DataFrame:
    path = MARKET_DIR / f"{name}.parquet"
    if not path.exists():
        raise DataError(f"缺少行情数据 {path.name}，请先运行 backend/scripts/download_data.py")
    return pd.read_parquet(path)


@lru_cache(maxsize=1)
def industry_names() -> dict[str, str]:
    df = read_dataset("industry_daily")
    return dict(df[["symbol", "name"]].drop_duplicates().itertuples(index=False))


def asset_type_of(symbol: str) -> AssetType:
    if symbol in STOCKS:
        return "stock"
    if is_futures(symbol):
        return "futures"
    if symbol in industry_names():
        return "industry"
    raise DataError(f"未知标的：{symbol}")


def symbol_name(symbol: str) -> str:
    t = asset_type_of(symbol)
    if t == "stock":
        return STOCKS[symbol].name
    if t == "industry":
        return industry_names()[symbol]
    spec = FUTURES_SPECS[symbol.removesuffix(NEXT_LEG_SUFFIX)]
    return spec.name + ("（次主力）" if symbol.endswith(NEXT_LEG_SUFFIX) else "")


def resolve_universe(spec: str | list[str]) -> list[str]:
    """把标的池描述解析成代码列表。

    支持：stock_pool / stocks（全部股票池）、industries（申万一级行业）、futures（全部商品期货）、
    以及逗号分隔的具体代码，例如 "600519,000858" 或 "RB,CU,RB.next"。
    """
    if isinstance(spec, list):
        items = spec
    else:
        key = spec.strip().lower()
        if key in ("stock_pool", "stocks", "a股", "沪深a股"):
            return list(STOCKS)
        if key in ("industries", "industry", "申万行业", "行业"):
            return sorted(industry_names())
        if key in ("futures", "commodities", "商品期货"):
            return list(FUTURES_SPECS)
        items = [s for s in spec.replace("，", ",").split(",")]
    out = []
    for s in (x.strip() for x in items):
        if not s:
            continue
        sym = s.upper() if is_futures(s.upper()) or s.upper().endswith(NEXT_LEG_SUFFIX.upper()) else s
        sym = sym.replace(".NEXT", NEXT_LEG_SUFFIX)
        asset_type_of(sym)
        out.append(sym)
    if not out:
        raise DataError("标的池为空")
    return list(dict.fromkeys(out))


@dataclass
class Bars:
    """多标的日线宽表。所有 DataFrame 的索引为交易日，列为标的代码。"""

    symbols: list[str]
    types: dict[str, AssetType]
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    exec_open: pd.DataFrame
    mark_close: pd.DataFrame
    mark_pre_close: pd.DataFrame
    tradable: pd.DataFrame  # 当日是否有行情（停牌为 False）
    roll: pd.DataFrame  # 期货当日是否换月
    contract: pd.DataFrame  # 期货当日实际交易的合约代码
    extra: dict[str, pd.DataFrame] = field(default_factory=dict)  # turnover、amount、close_raw 等

    @property
    def dates(self) -> pd.DatetimeIndex:
        return self.close.index

    def returns(self) -> pd.DataFrame:
        """日收益率（用执行价体系计算，期货换月当天不含价差）。"""
        r = self.mark_close / self.mark_pre_close - 1
        return r.where(self.tradable)


def _wide(df: pd.DataFrame, col: str, index: pd.DatetimeIndex, symbols: list[str]) -> pd.DataFrame:
    w = df.pivot(index="date", columns="symbol", values=col)
    return w.reindex(index=index, columns=symbols)


def load_bars(symbols: list[str], end: str | pd.Timestamp | None = None) -> Bars:
    """加载 symbols 自有数据以来到 end 的全部日线。指标需要的预热期由策略自行利用。"""
    end_ts = pd.Timestamp(end) if end is not None else None
    types = {s: asset_type_of(s) for s in symbols}
    frames = []
    by_type: dict[str, list[str]] = {}
    for s, t in types.items():
        by_type.setdefault(t, []).append(s)

    if "stock" in by_type:
        df = read_dataset("stock_daily")
        df = df[df["symbol"].isin(by_type["stock"])].copy()
        df = df.sort_values(["symbol", "date"])
        df["exec_open"] = df["open"]
        df["mark_close"] = df["close"]
        df["mark_pre_close"] = df.groupby("symbol")["close"].shift()
        df["roll"] = False
        df["contract"] = df["symbol"]
        frames.append(df)
    if "industry" in by_type:
        df = read_dataset("industry_daily")
        df = df[df["symbol"].isin(by_type["industry"])].drop(columns="name").copy()
        df = df.sort_values(["symbol", "date"])
        df["exec_open"] = df["open"]
        df["mark_close"] = df["close"]
        df["mark_pre_close"] = df.groupby("symbol")["close"].shift()
        df["roll"] = False
        df["contract"] = df["symbol"]
        frames.append(df)
    if "futures" in by_type:
        df = read_dataset("futures_continuous")
        df = df[df["symbol"].isin(by_type["futures"])].copy()
        df["exec_open"] = df["open"]
        df["mark_close"] = df["close"]
        df["mark_pre_close"] = df["pre_close"]
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] * df["adj_factor"]
        frames.append(df)

    data = pd.concat(frames, ignore_index=True)
    data["date"] = pd.to_datetime(data["date"])
    if end_ts is not None:
        data = data[data["date"] <= end_ts]
    missing = [s for s in symbols if s not in set(data["symbol"])]
    if missing:
        raise DataError(f"以下标的在数据快照中没有行情：{', '.join(missing)}")

    index = pd.DatetimeIndex(sorted(data["date"].unique()), name="date")
    w = lambda col: _wide(data, col, index, symbols)  # noqa: E731
    tradable = w("close").notna()
    mark_close = w("mark_close").ffill()
    mark_pre = w("mark_pre_close")
    extra = {}
    for col in ("turnover", "amount", "close_raw", "hold"):
        if col in data.columns:
            extra[col] = w(col)
    return Bars(
        symbols=symbols,
        types=types,
        open=w("open"),
        high=w("high"),
        low=w("low"),
        close=w("close"),
        volume=w("volume"),
        exec_open=w("exec_open"),
        mark_close=mark_close,
        mark_pre_close=mark_pre,
        tradable=tradable,
        roll=w("roll").fillna(False).astype(bool),
        contract=w("contract"),
        extra=extra,
    )


def load_benchmarks(codes: list[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """基准指数收盘价宽表（列为指数代码）。"""
    df = read_dataset("index_daily")
    df = df[df["symbol"].isin(codes)]
    w = df.pivot(index="date", columns="symbol", values="close").sort_index()
    w.index = pd.to_datetime(w.index)
    return w.loc[start:end, [c for c in codes if c in w.columns]]


def load_dividends() -> pd.DataFrame:
    return read_dataset("dividends")


def data_range() -> dict[str, tuple[str, str]]:
    """各类资产的数据起止日期，供智能体校验用户给出的回测区间。"""
    out = {}
    for name, label in (("stock_daily", "stock"), ("industry_daily", "industry"),
                        ("futures_continuous", "futures"), ("index_daily", "index")):
        try:
            d = pd.to_datetime(read_dataset(name)["date"])
            out[label] = (str(d.min().date()), str(d.max().date()))
        except DataError:
            continue
    return out
