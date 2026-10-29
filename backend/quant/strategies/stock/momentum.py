from typing import Literal

from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, top_k_weights
from ..indicators import momentum


class Params(StrategyParams):
    lookback: int = Field(120, ge=10, le=250, title="动量回看期",
                          description="用过去多少个交易日的涨幅衡量动量，常见 60~250 日")
    skip: int = Field(20, ge=0, le=60, title="跳过近期天数",
                      description="计算动量时剔除最近若干天，规避短期反转效应（经典做法跳过最近一个月）")
    top_k: int = Field(10, ge=1, le=30, title="持股数量", description="每次调仓买入动量最强的前 K 只股票")
    rebalance: Literal["W", "M", "Q"] = Field("M", title="调仓频率", description="W 每周、M 每月、Q 每季度")
    abs_filter: bool = Field(False, title="绝对动量过滤",
                             description="开启后只买入动量为正的股票，全部为负时空仓（双动量思想，可降低熊市回撤）")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例", description="满仓时股票占总资金的比例")


@register
class MomentumStock(Strategy):
    id = "momentum_stock"
    name = "动量选股"
    category = "stock"
    style = "截面动量"
    summary = "定期买入过去一段时间涨得最多的股票，押注强者恒强。"
    aliases = ("动量", "动量策略", "强者恒强", "截面动量")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})
    min_symbols = 3

    def generate(self, bars):
        p = self.params
        score = momentum(bars.close, p.lookback, p.skip).where(bars.tradable)
        if p.abs_filter:
            score = score.where(score > 0)
        mask = rebalance_mask(bars.dates, p.rebalance)
        w = top_k_weights(score, min(p.top_k, len(bars.symbols)), mask, p.position_ratio)
        return StrategyOutput(weights=w, rebalance=mask, indicators={"动量": score})
