from typing import Literal

from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, top_k_weights
from ..indicators import momentum


class Params(StrategyParams):
    lookback: int = Field(5, ge=1, le=60, title="反转回看期", description="用过去多少个交易日的涨跌幅排名，反转效应通常在 1~4 周内最明显")
    top_k: int = Field(3, ge=1, le=8, title="每边品种数", description="做多跌得最多的 K 个、做空涨得最多的 K 个")
    position_limit: float = Field(0.1, gt=0, le=0.5, title="单品种仓位", description="每个入选品种名义市值占权益的比例")
    rebalance: Literal["W", "M"] = Field("W", title="调仓频率", description="W 每周、M 每月")


@register
class ReversalFutures(Strategy):
    id = "reversal_futures"
    name = "期货短期反转"
    category = "futures"
    style = "截面反转（多空对冲）"
    summary = "做多近期跌幅最大的品种、做空涨幅最大的品种，押注短期过度反应会被修正。与截面动量方向正好相反，可以对照学习。"
    aliases = ("期货反转", "期货短期反转", "短期反转期货", "截面反转")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})
    min_symbols = 4

    def generate(self, bars):
        p = self.params
        score = momentum(bars.close, p.lookback).where(bars.tradable)
        k = min(p.top_k, len(bars.symbols) // 2)
        mask = rebalance_mask(bars.dates, p.rebalance)
        long = top_k_weights(score, k, mask, k * p.position_limit, ascending=True)
        short = top_k_weights(score, k, mask, k * p.position_limit)
        return StrategyOutput(weights=long - short, rebalance=mask, indicators={"近期涨跌幅": score})
