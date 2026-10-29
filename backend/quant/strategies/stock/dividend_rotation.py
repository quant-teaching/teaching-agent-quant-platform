from typing import Literal

from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, top_k_weights
from ..indicators import sma
from .multi_factor import trailing_dividend_yield


class Params(StrategyParams):
    top_k: int = Field(10, ge=1, le=30, title="持股数量", description="买入股息率最高的前 K 只股票")
    min_yield: float = Field(0.02, ge=0, le=0.1, title="最低股息率", description="股息率低于该值的股票不入选")
    rebalance: Literal["M", "Q"] = Field("Q", title="调仓频率",
                                         description="分红一年一到两次，股息率变化慢，按季度调仓即可")
    trend_filter: int = Field(0, ge=0, le=250, title="趋势过滤均线",
                              description="只买收盘价在该均线之上的股票，避开股价持续下跌造成的'高股息陷阱'，0 表示不过滤")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例", description="满仓时股票占总资金的比例")


@register
class DividendRotation(Strategy):
    id = "dividend_rotation"
    name = "股息率轮动"
    category = "stock"
    style = "价值 / 红利"
    summary = "定期买入过去一年股息率最高的股票，获取稳定分红并享受高股息股票的估值修复。"
    aliases = ("股息率", "红利", "高股息", "股息轮动", "红利轮动")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock"})
    min_symbols = 3

    def generate(self, bars):
        p = self.params
        dy = trailing_dividend_yield(bars).where(bars.tradable)
        score = dy.where(dy >= p.min_yield)
        if p.trend_filter:
            score = score.where(bars.close > sma(bars.close, p.trend_filter))
        mask = rebalance_mask(bars.dates, p.rebalance)
        w = top_k_weights(score, min(p.top_k, len(bars.symbols)), mask, p.position_ratio)
        return StrategyOutput(weights=w, rebalance=mask, indicators={"股息率": dy})
