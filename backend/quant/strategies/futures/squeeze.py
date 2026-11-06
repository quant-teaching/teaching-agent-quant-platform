from pydantic import Field

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, state_machine
from ..indicators import bollinger


class Params(StopParams):
    bb_window: int = Field(20, ge=5, le=120, title="布林带周期", description="布林带中轨均线天数")
    bb_k: float = Field(2.0, gt=0, le=4, title="标准差倍数", description="上下轨距离中轨几个标准差")
    squeeze_lookback: int = Field(120, ge=20, le=500, title="收口比较期",
                                  description="把当前带宽和过去多少天比较，判断是否处于历史低位")
    squeeze_pct: float = Field(0.2, gt=0, lt=1, title="收口分位",
                               description="带宽处在过去比较期的最低多少分位以内算'收口'，越小越严格")
    memory: int = Field(10, ge=1, le=60, title="收口记忆天数", description="收口结束后多少天内出现的突破仍然有效")
    position_limit: float = Field(0.1, gt=0, le=1, title="单品种仓位上限", description="单个品种名义市值占权益的比例")
    allow_short: bool = Field(True, title="允许做空", description="关闭后只做向上突破")


@register
class SqueezeFutures(Strategy):
    id = "squeeze_futures"
    name = "布林带收口突破"
    category = "futures"
    style = "波动率策略（收缩后扩张）"
    summary = "波动率有'收缩之后必有扩张'的规律：布林带宽度降到历史低位（收口）后，价格突破上轨做多、跌破下轨做空，回到中轨离场。"
    aliases = ("布林收口", "收口突破", "挤压突破", "squeeze", "波动率收缩", "布林带收口")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        mid, up, lo = bollinger(c, p.bb_window, p.bb_k)
        width = (up - lo) / mid
        rank = width.rolling(p.squeeze_lookback, min_periods=p.squeeze_lookback).rank(pct=True)
        squeezed = (rank <= p.squeeze_pct).astype(float).where(rank.notna())
        recent = squeezed.rolling(p.memory, min_periods=1).max() > 0
        pos = state_machine(recent & (c > up), c < mid,
                            (recent & (c < lo)) if p.allow_short else None, c > mid)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pos * p.position_limit,
                              indicators={"上轨": up, "中轨": mid, "下轨": lo, "带宽": width, "带宽分位": rank})
