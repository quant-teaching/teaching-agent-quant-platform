from typing import Literal

from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, top_k_weights
from ..indicators import momentum


class Params(StrategyParams):
    lookback: int = Field(60, ge=5, le=250, title="动量回看期", description="用过去多少个交易日的涨跌幅给品种排名")
    skip: int = Field(0, ge=0, le=20, title="跳过近期天数", description="计算动量时剔除最近若干天，减少短期反转干扰")
    top_k: int = Field(3, ge=1, le=8, title="每边品种数", description="做多排名最前的 K 个、做空排名最后的 K 个")
    position_limit: float = Field(0.1, gt=0, le=0.5, title="单品种仓位", description="每个入选品种名义市值占权益的比例")
    rebalance: Literal["W", "M"] = Field("W", title="调仓频率", description="W 每周、M 每月")


@register
class CrossSectionMomentumFutures(Strategy):
    id = "cs_momentum_futures"
    name = "期货截面动量"
    category = "futures"
    style = "截面动量（多空对冲）"
    summary = "定期给所有品种按过去一段时间的涨幅排名，做多最强的几个、做空最弱的几个，赚'相对强弱'的钱，对整体涨跌不敏感。"
    aliases = ("截面动量期货", "期货截面动量", "期货动量", "多空动量", "品种轮动", "期货动量轮动")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})
    min_symbols = 4

    def generate(self, bars):
        p = self.params
        score = momentum(bars.close, p.lookback, p.skip).where(bars.tradable)
        k = min(p.top_k, len(bars.symbols) // 2)
        mask = rebalance_mask(bars.dates, p.rebalance)
        long = top_k_weights(score, k, mask, k * p.position_limit)
        short = top_k_weights(score, k, mask, k * p.position_limit, ascending=True)
        return StrategyOutput(weights=long - short, rebalance=mask, indicators={"动量": score})
