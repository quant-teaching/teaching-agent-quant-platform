from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, state_machine
from ..indicators import kama


class Params(StopParams):
    er_window: int = Field(10, ge=3, le=60, title="效率比周期", description="计算效率比 ER 的天数，考夫曼原版 10")
    fast: int = Field(2, ge=2, le=10, title="最快周期", description="趋势最清晰（ER = 1）时 KAMA 相当于几日 EMA")
    slow: int = Field(30, ge=10, le=120, title="最慢周期", description="完全震荡（ER = 0）时 KAMA 相当于几日 EMA")
    band: float = Field(0.01, ge=0, le=0.1, title="过滤带宽",
                        description="价格高出 KAMA 该比例才做多、低于才做空，回到 KAMA 平仓，用于过滤贴线抖动")
    position_limit: float = Field(0.1, gt=0, le=1, title="单品种仓位上限", description="单个品种名义市值占权益的比例")
    allow_short: bool = Field(True, title="允许做空", description="关闭后只做多")

    @model_validator(mode="after")
    def _check(self):
        if self.fast >= self.slow:
            raise ValueError("最快周期必须小于最慢周期")
        return self


@register
class KAMAFutures(Strategy):
    id = "kama_futures"
    name = "考夫曼自适应均线"
    category = "futures"
    style = "趋势跟踪（自适应）"
    summary = "KAMA 根据'效率比'自动调节速度：趋势清晰时像短均线一样紧跟价格，震荡时像长均线一样几乎不动，以减少震荡市的假信号。"
    aliases = ("KAMA", "考夫曼", "自适应均线", "AMA", "考夫曼均线")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        k = kama(c, p.er_window, p.fast, p.slow)
        pos = state_machine(c > k * (1 + p.band), c < k,
                            (c < k * (1 - p.band)) if p.allow_short else None, c > k)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pos * p.position_limit, indicators={"KAMA": k})
