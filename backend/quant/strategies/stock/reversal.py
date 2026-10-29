from typing import Literal

from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, top_k_weights
from ..indicators import momentum, realized_vol


class Params(StrategyParams):
    lookback: int = Field(5, ge=1, le=60, title="反转回看期",
                          description="用过去多少个交易日的涨跌幅衡量超跌程度，短期反转常用 5~20 日")
    top_k: int = Field(10, ge=1, le=30, title="持股数量", description="每次调仓买入跌得最多的前 K 只股票")
    rebalance: Literal["W", "M"] = Field("W", title="调仓频率", description="反转效应持续时间短，通常按周调仓")
    vol_filter: float = Field(0.0, ge=0, le=2, title="波动率上限",
                              description="剔除 60 日年化波动率高于该值的股票（避免接飞刀），0 表示不过滤")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例", description="满仓时股票占总资金的比例")


@register
class ReversalStock(Strategy):
    id = "reversal_stock"
    name = "反转策略"
    category = "stock"
    style = "截面反转"
    summary = "定期买入近期跌得最多的股票，押注短期超跌后的价格修复。"
    aliases = ("反转", "短期反转", "超跌反弹", "均值回复选股")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})
    min_symbols = 3

    def generate(self, bars):
        p = self.params
        ret = momentum(bars.close, p.lookback).where(bars.tradable)
        if p.vol_filter > 0:
            ret = ret.where(realized_vol(bars.close, 60) <= p.vol_filter)
        mask = rebalance_mask(bars.dates, p.rebalance)
        w = top_k_weights(ret, min(p.top_k, len(bars.symbols)), mask, p.position_ratio, ascending=True)
        return StrategyOutput(weights=w, rebalance=mask, indicators={"近期涨跌幅": ret})
