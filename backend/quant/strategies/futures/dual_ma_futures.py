from typing import Literal

from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, state_machine
from ..indicators import cross_down, cross_up, ema, sma


class Params(StopParams):
    fast: int = Field(10, ge=2, le=120, title="短均线周期", description="短期均线天数")
    slow: int = Field(40, ge=5, le=250, title="长均线周期", description="长期均线天数")
    ma_type: Literal["SMA", "EMA"] = Field("EMA", title="均线类型", description="SMA 简单平均；EMA 指数平均")
    position_limit: float = Field(0.1, gt=0, le=1, title="单品种仓位上限",
                                  description="单个品种名义市值占权益的比例。该策略始终持仓，16 个品种合计名义杠杆约为 16 × 该值")
    allow_short: bool = Field(True, title="允许做空", description="关闭后死叉只平多不开空")

    @model_validator(mode="after")
    def _check(self):
        if self.fast >= self.slow:
            raise ValueError("短均线周期必须小于长均线周期")
        return self


@register
class DualMAFutures(Strategy):
    id = "dual_ma_futures"
    name = "双均线期货策略"
    category = "futures"
    style = "趋势跟踪"
    summary = "金叉做多、死叉做空，始终站在均线趋势一侧，多空双向的双均线系统。"
    aliases = ("双均线期货", "期货双均线", "均线交叉期货")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        ma = sma if p.ma_type == "SMA" else ema
        fast, slow = ma(bars.close, p.fast), ma(bars.close, p.slow)
        up = cross_up(fast, slow) | (fast > slow)
        dn = cross_down(fast, slow) | (fast < slow)
        pos = state_machine(up, dn, dn if p.allow_short else None, up)
        pos = apply_stops(pos, bars.close, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pos * p.position_limit,
                              indicators={f"MA{p.fast}": fast, f"MA{p.slow}": slow})
