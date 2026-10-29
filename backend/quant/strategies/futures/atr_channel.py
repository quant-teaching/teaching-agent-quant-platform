from pydantic import Field

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, state_machine
from ..indicators import atr, sma


class Params(StopParams):
    ma_window: int = Field(20, ge=5, le=120, title="中轨均线周期", description="通道中轨的均线天数")
    atr_period: int = Field(14, ge=5, le=60, title="ATR 周期", description="衡量波动幅度的天数")
    atr_mult: float = Field(2.0, gt=0, le=6, title="ATR 倍数",
                            description="上下轨 = 中轨 ± 倍数 × ATR，倍数越大越不容易被噪音触发")
    position_limit: float = Field(0.2, gt=0, le=1, title="单品种仓位上限",
                                  description="单个品种名义市值占权益的比例")
    allow_short: bool = Field(True, title="允许做空", description="关闭后只做多头突破")


@register
class ATRChannelFutures(Strategy):
    id = "atr_channel_futures"
    name = "ATR 通道突破"
    category = "futures"
    style = "趋势跟踪（波动率通道）"
    summary = "以均线 ± k 倍 ATR 构成通道，收盘突破上轨做多、跌破下轨做空，回到中轨离场。"
    aliases = ("ATR通道", "ATR突破", "凯特纳通道", "ATR 通道突破")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        mid = sma(c, p.ma_window)
        a = atr(bars.high, bars.low, c, p.atr_period)
        up, lo = mid + p.atr_mult * a, mid - p.atr_mult * a
        pos = state_machine(c > up, c < mid, (c < lo) if p.allow_short else None, c > mid)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pos * p.position_limit,
                              indicators={"上轨": up, "中轨": mid, "下轨": lo})
