from typing import Literal

from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, top_k_weights
from ..indicators import realized_vol


class Params(StrategyParams):
    vol_window: int = Field(60, ge=20, le=250, title="波动率窗口", description="用过去多少个交易日的日收益波动衡量风险")
    top_k: int = Field(10, ge=1, le=30, title="持股数量", description="每次调仓买入波动率最低的前 K 只股票")
    rebalance: Literal["W", "M", "Q"] = Field("M", title="调仓频率", description="W 每周、M 每月、Q 每季度")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例", description="满仓时股票占总资金的比例")


@register
class LowVolStock(Strategy):
    id = "low_vol_stock"
    name = "低波动选股"
    category = "stock"
    style = "截面选股（低波动异象）"
    summary = "定期买入过去一段时间波动最小的股票。学术研究发现低波动股票的风险调整后收益长期并不比高波动股票差（低波动异象）。"
    aliases = ("低波动", "低波", "低波动选股", "低波动异象", "最小波动")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})
    min_symbols = 3

    def generate(self, bars):
        p = self.params
        vol = realized_vol(bars.close, p.vol_window)
        # 窗口内数据不足一半的（新股、长期停牌）不参与排序
        score = vol.where(bars.tradable & bars.close.rolling(p.vol_window, min_periods=p.vol_window).count().ge(p.vol_window))
        mask = rebalance_mask(bars.dates, p.rebalance)
        w = top_k_weights(score, min(p.top_k, len(bars.symbols)), mask, p.position_ratio, ascending=True)
        return StrategyOutput(weights=w, rebalance=mask, indicators={"年化波动率": vol})
