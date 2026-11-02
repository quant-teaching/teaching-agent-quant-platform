"""行情加载：把股票、行业指数、期货统一成"日期 × 标的"的宽表。

两套价格：
- open / high / low / close：用于计算技术指标。股票为前复权价，期货为比例后复权价，
  这样分红除权、期货换月都不会在指标里制造假突破。
- exec_open / mark_close / mark_pre_close：用于成交和盯市，都是真实价格。股票按当日不复权价成交、
  按 100 股一手取整，分红以现金入账、送转股增加持股数量（见 corporate_actions）；
  期货用当日实际交易合约的原始价格，盈亏 = 手数 × 乘数 × 原始价差。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
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

    def truncate(self, end: str | pd.Timestamp) -> Bars:
        """截取 end 及以前的数据（返回新对象，不修改缓存中的原始数据）。"""
        end_ts = pd.Timestamp(end)
        cut = lambda df: df.loc[:end_ts]  # noqa: E731
        return replace(
            self, open=cut(self.open), high=cut(self.high), low=cut(self.low), close=cut(self.close),
            volume=cut(self.volume), exec_open=cut(self.exec_open), mark_close=cut(self.mark_close),
            mark_pre_close=cut(self.mark_pre_close), tradable=cut(self.tradable), roll=cut(self.roll),
            contract=cut(self.contract), extra={k: cut(v) for k, v in self.extra.items()},
        )

    def returns(self) -> pd.DataFrame:
        """日收益率：股票用复权价（含分红送转），期货用实际合约价（换月当天不含价差）。"""
        r = self.mark_close / self.mark_pre_close - 1
        adj_pre = self.extra.get("adj_pre_close")
        if adj_pre is not None:
            cols = [s for s in self.symbols if self.types[s] == "stock"]
            r[cols] = self.close[cols] / adj_pre[cols] - 1
        return r.where(self.tradable)


def _wide(df: pd.DataFrame, col: str, index: pd.DatetimeIndex, symbols: list[str]) -> pd.DataFrame:
    w = df.pivot(index="date", columns="symbol", values=col)
    return w.reindex(index=index, columns=symbols)


def load_bars(symbols: list[str], end: str | pd.Timestamp | None = None) -> Bars:
    """加载 symbols 自有数据以来到 end 的全部日线。指标需要的预热期由策略自行利用。

    全部历史按标的池缓存：同一标的池反复回测（不同区间、参数对比、组合）时不再重复整理宽表。
    回测时直接使用全部历史即可，引擎只撮合区间内的交易日；策略信号只依赖过去的数据
    （见 tests/test_strategies.py::test_no_lookahead），所以多出的未来数据不影响结果。
    返回的 Bars 被多次回测共享，策略和引擎只能读取、不能原地修改。
    """
    full = _load_bars(tuple(symbols))
    return full if end is None else full.truncate(end)


@lru_cache(maxsize=16)
def _load_bars(symbols_t: tuple[str, ...]) -> Bars:
    symbols = list(symbols_t)
    end_ts = None
    types = {s: asset_type_of(s) for s in symbols}
    frames = []
    by_type: dict[str, list[str]] = {}
    for s, t in types.items():
        by_type.setdefault(t, []).append(s)

    if "stock" in by_type:
        df = read_dataset("stock_daily")
        df = df[df["symbol"].isin(by_type["stock"])].copy()
        df = df.sort_values(["symbol", "date"])
        frames.append(corporate_actions(df))
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
    present = set(data["symbol"].unique())
    missing = [s for s in symbols if s not in present]
    if missing:
        raise DataError(f"以下标的在数据快照中没有行情：{', '.join(missing)}")

    index = pd.DatetimeIndex(sorted(data["date"].unique()), name="date")
    w = lambda col: _wide(data, col, index, symbols)  # noqa: E731
    tradable = w("close").notna()
    mark_close = w("mark_close").ffill()
    mark_pre = w("mark_pre_close")
    extra = {}
    for col in ("turnover", "amount", "close_raw", "hold", "adj_pre_close", "cash_div", "split"):
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


SPLIT_MIN = 0.03  # 复权比例变化超过 3% 且现金分红解释不了时，认定为送转股


def corporate_actions(df: pd.DataFrame) -> pd.DataFrame:
    """股票真实成交价与分红送转。df 为单类股票日线（按 symbol、date 排序），返回补充列后的副本。

    行情里只有前复权 OHLC 和不复权收盘价 close_raw，同一天两者之比就是当日复权系数，
    由此还原不复权开盘价。相邻两个交易日（p → t，中间可能停牌）之间：
        现金分红 D = 除权日落在 (p, t] 内的每股派息之和；
        送转比例 m = (raw_p × adj_t / adj_p − D) / raw_t ，即复权收益扣掉现金分红后，由股数变多解释的部分；
        m 偏离 1 不足 3% 时视为价格取整误差（m = 1），否则按 0.1 取整（10 送 3 → 1.3）。
    除权参考价 = (raw_p − D) / m ，用于判断 t 日开盘是否涨跌停。
    """
    df = df.copy()
    factor = df["close_raw"] / df["close"]
    df["exec_open"] = (df["open"] * factor).round(2)
    df["mark_close"] = df["close_raw"]
    g = df.groupby("symbol", sort=False)
    raw_p = g["close_raw"].shift()
    adj_p = g["close"].shift()

    # 每个除权日落到它当天或之后的第一个交易日（停牌期间除权的，复牌当天入账）
    div = load_dividends()
    div = div[div["symbol"].isin(df["symbol"].unique())]
    cash = pd.Series(0.0, index=df.index)
    dates = pd.to_datetime(df["date"])
    for sym, events in div.groupby("symbol"):
        rows = df.index[df["symbol"] == sym]
        d = dates[rows].to_numpy()
        pos = d.searchsorted(pd.to_datetime(events["ex_date"]).to_numpy())
        ok = (pos > 0) & (pos < len(d))  # 第一个交易日之前的除权与持仓无关
        hits = pd.Series(events["cash_per_share"].to_numpy()[ok]).groupby(pos[ok]).sum()
        cash[rows[hits.index]] += hits.to_numpy()
    m = (raw_p * df["close"] / adj_p - cash) / df["close_raw"]
    split = m.where((m - 1).abs() >= SPLIT_MIN, 1.0).round(1).fillna(1.0)
    split = split.where(split >= 1.0, 1.0)  # 缩股在 A 股极少见，数据噪声导致的 m<1 一律忽略
    df["cash_div"] = cash
    df["split"] = split
    df["mark_pre_close"] = (raw_p - cash) / split
    df["adj_pre_close"] = adj_p
    df["roll"] = False
    df["contract"] = df["symbol"]
    return df


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
