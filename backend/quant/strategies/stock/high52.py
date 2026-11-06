from typing import Literal

from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, top_k_weights


class Params(StrategyParams):
    window: int = Field(250, ge=60, le=500, title="高点回看期", description="与过去多少个交易日的最高收盘价比较，250 日约为 52 周")
    top_k: int = Field(10, ge=1, le=30, title="持股数量", description="买入离高点最近的前 K 只股票")
    min_ratio: float = Field(0.0, ge=0, le=1, title="最低接近度",
                             description="收盘价 / 区间最高价低于该值的股票不入选，0 表示不限制")
    rebalance: Literal["W", "M", "Q"] = Field("M", title="调仓频率", description="W 每周、M 每月、Q 每季度")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例", description="满仓时股票占总资金的比例")


@register
class High52Stock(Strategy):
    id = "high52_stock"
    name = "52 周新高选股"
    category = "stock"
    style = "截面动量"
    summary = "定期买入收盘价最接近过去一年最高价的股票。投资者常把历史高点当作'锚'而迟迟不敢追，导致接近高点的股票被低估。"
    aliases = ("52周新高", "52 周新高", "新高选股", "接近新高", "一年新高", "52周高点")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})
    min_symbols = 3

    def generate(self, bars):
        p = self.params
        c = bars.close
        ratio = c / c.rolling(p.window, min_periods=p.window).max()
        score = ratio.where(bars.tradable & (ratio >= p.min_ratio))
        mask = rebalance_mask(bars.dates, p.rebalance)
        w = top_k_weights(score, min(p.top_k, len(bars.symbols)), mask, p.position_ratio)
        return StrategyOutput(weights=w, rebalance=mask, indicators={"接近度": ratio})
