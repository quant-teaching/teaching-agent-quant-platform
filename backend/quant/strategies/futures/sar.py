from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..indicators import parabolic_sar


class Params(StrategyParams):
    af_step: float = Field(0.02, gt=0, le=0.1, title="加速因子步长",
                           description="趋势每创一次新极值，SAR 向价格靠拢的速度增加多少，威尔德原版 0.02")
    af_max: float = Field(0.2, gt=0, le=0.5, title="加速因子上限", description="加速因子的最大值，原版 0.2")
    position_limit: float = Field(0.1, gt=0, le=1, title="单品种仓位上限", description="单个品种名义市值占权益的比例")
    allow_short: bool = Field(True, title="允许做空", description="关闭后 SAR 翻空时只平仓、不反手做空")

    @model_validator(mode="after")
    def _check(self):
        if self.af_step > self.af_max:
            raise ValueError("加速因子步长不能大于上限")
        return self


@register
class ParabolicSARFutures(Strategy):
    id = "sar_futures"
    name = "抛物线 SAR"
    category = "futures"
    style = "趋势跟踪（跟踪止损）"
    summary = "SAR 是一条随时间加速逼近价格的跟踪止损线：价格在 SAR 之上做多、之下做空，被击穿就立即反手（停损转向）。"
    aliases = ("SAR", "抛物线", "抛物线SAR", "停损转向", "parabolic sar", "PSAR")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        sar, trend = parabolic_sar(bars.high, bars.low, p.af_step, p.af_max)
        pos = trend.clip(lower=None if p.allow_short else 0)
        return StrategyOutput(weights=pos * p.position_limit, indicators={"SAR": sar})
