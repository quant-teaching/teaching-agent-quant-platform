from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, state_machine
from ..indicators import dmi


class Params(StopParams):
    period: int = Field(14, ge=5, le=60, title="DMI 周期", description="计算 ±DI 和 ADX 的威尔德平滑天数，经典取 14")
    adx_entry: float = Field(25, ge=10, le=60, title="趋势成立阈值", description="ADX 高于该值才认为有趋势，才允许开仓")
    adx_exit: float = Field(20, ge=5, le=50, title="趋势消失阈值", description="ADX 跌破该值认为趋势减弱，平仓离场")
    position_limit: float = Field(0.1, gt=0, le=1, title="单品种仓位上限", description="单个品种名义市值占权益的比例")
    allow_short: bool = Field(True, title="允许做空", description="关闭后只做多头趋势")

    @model_validator(mode="after")
    def _check(self):
        if self.adx_exit >= self.adx_entry:
            raise ValueError("趋势消失阈值必须小于趋势成立阈值")
        return self


@register
class ADXFutures(Strategy):
    id = "adx_futures"
    name = "DMI/ADX 趋势强度"
    category = "futures"
    style = "趋势跟踪（趋势强度过滤）"
    summary = "ADX 衡量'有没有趋势'，±DI 判断'趋势朝哪边'：ADX 高于阈值且 +DI > −DI 做多、−DI > +DI 做空，ADX 回落或方向翻转时平仓。"
    aliases = ("ADX", "DMI", "趋向指标", "趋势强度", "ADX趋势", "DMI趋势")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        pdi, mdi, adx = dmi(bars.high, bars.low, bars.close, p.period)
        strong = adx > p.adx_entry
        weak = adx < p.adx_exit
        pos = state_machine(strong & (pdi > mdi), weak | (pdi < mdi),
                            (strong & (mdi > pdi)) if p.allow_short else None, weak | (mdi < pdi))
        pos = apply_stops(pos, bars.close, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pos * p.position_limit, indicators={"+DI": pdi, "−DI": mdi, "ADX": adx})
