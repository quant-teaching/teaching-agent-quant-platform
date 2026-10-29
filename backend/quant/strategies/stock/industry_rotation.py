from typing import Literal

from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, top_k_weights
from ..indicators import momentum, sma


class Params(StrategyParams):
    lookback: int = Field(20, ge=5, le=250, title="动量回看期", description="比较各行业过去多少个交易日的涨幅")
    top_k: int = Field(3, ge=1, le=10, title="持有行业数", description="每次调仓持有涨幅最强的前 K 个行业")
    rebalance: Literal["W", "M"] = Field("M", title="调仓频率", description="W 每周、M 每月")
    trend_filter: int = Field(0, ge=0, le=250, title="趋势过滤均线",
                              description="只持有收盘价在该均线之上的行业，0 表示不过滤")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例", description="满仓时占总资金的比例")


@register
class IndustryRotation(Strategy):
    id = "industry_rotation"
    name = "行业轮动"
    category = "stock"
    style = "行业动量轮动"
    summary = "比较申万一级行业指数的近期涨幅，定期切换到最强的几个行业，追随市场主线。"
    aliases = ("行业轮动", "板块轮动", "行业动量")
    Params = Params
    default_universe = "industries"
    asset_types = frozenset({"industry"})
    min_symbols = 3

    def generate(self, bars):
        p = self.params
        score = momentum(bars.close, p.lookback).where(bars.tradable)
        if p.trend_filter:
            score = score.where(bars.close > sma(bars.close, p.trend_filter))
        mask = rebalance_mask(bars.dates, p.rebalance)
        w = top_k_weights(score, min(p.top_k, len(bars.symbols)), mask, p.position_ratio)
        return StrategyOutput(
            weights=w, rebalance=mask, indicators={"行业动量": score},
            notes=["行业指数本身不能直接交易，回测中把它当作对应的行业 ETF 处理（教学近似）。"],
        )
