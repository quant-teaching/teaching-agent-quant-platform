from typing import Literal

from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, weighted_on_mask


class Params(StrategyParams):
    rebalance: Literal["M", "Q", "Y"] = Field("Q", title="再平衡频率",
                                              description="M 每月、Q 每季度、Y 每年把各标的拉回相同权重")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例", description="满仓时股票占总资金的比例")


@register
class EqualWeightStock(Strategy):
    id = "equal_weight_stock"
    name = "等权定期再平衡"
    category = "stock"
    style = "资产配置（基准）"
    summary = "把资金平均分给标的池里的每只股票，定期卖出涨多的、买入跌多的，拉回等权。它是检验其他选股策略是否真有本事的'朴素基准'。"
    aliases = ("等权", "等权组合", "再平衡", "定期再平衡", "等权再平衡", "1/N")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})
    min_symbols = 2

    def generate(self, bars):
        p = self.params
        live = bars.tradable.astype(float)
        raw = live.div(live.sum(axis=1).replace(0, float("nan")), axis=0) * p.position_ratio
        mask = rebalance_mask(bars.dates, p.rebalance)
        return StrategyOutput(weights=weighted_on_mask(raw, mask), rebalance=mask)
