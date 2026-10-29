from typing import Literal

from pydantic import Field

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, state_machine
from ..indicators import sma


class Params(StopParams):
    window: int = Field(20, ge=5, le=120, title="通道均线周期", description="分别对最高价、最低价求均线的天数")
    exit_mode: Literal["reverse", "middle"] = Field("reverse", title="离场方式",
                           description="reverse：价格穿越另一侧通道时反手；middle：回到通道中线即平仓")
    position_limit: float = Field(0.2, gt=0, le=1, title="单品种仓位上限",
                                  description="单个品种名义市值占权益的比例")
    allow_short: bool = Field(True, title="允许做空", description="关闭后只做多")


@register
class MAChannelFutures(Strategy):
    id = "ma_channel_futures"
    name = "移动平均通道"
    category = "futures"
    style = "趋势跟踪（均线通道）"
    summary = "用最高价均线和最低价均线围成通道，收盘站上通道上沿做多、跌破下沿做空。"
    aliases = ("移动平均通道", "均线通道", "高低点均线通道", "MA通道")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        up, lo = sma(bars.high, p.window), sma(bars.low, p.window)
        mid = (up + lo) / 2
        if p.exit_mode == "middle":
            pos = state_machine(c > up, c < mid, (c < lo) if p.allow_short else None, c > mid)
        else:
            pos = state_machine(c > up, c < lo, (c < lo) if p.allow_short else None, c > up)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pos * p.position_limit, indicators={"通道上沿": up, "通道中线": mid,
                                                                          "通道下沿": lo})
