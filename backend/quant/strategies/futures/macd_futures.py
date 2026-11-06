from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, state_machine
from ..indicators import macd


class Params(StopParams):
    fast: int = Field(12, ge=2, le=60, title="快线周期", description="DIF 中快速 EMA 的天数")
    slow: int = Field(26, ge=5, le=120, title="慢线周期", description="DIF 中慢速 EMA 的天数")
    signal: int = Field(9, ge=2, le=60, title="信号线周期", description="DEA 是 DIF 的 EMA，天数越大信号越少")
    zero_filter: bool = Field(True, title="零轴过滤",
                              description="开启后只在 DIF > 0 时做多金叉、DIF < 0 时做空死叉，顺着大方向交易")
    position_limit: float = Field(0.1, gt=0, le=1, title="单品种仓位上限", description="单个品种名义市值占权益的比例")
    allow_short: bool = Field(True, title="允许做空", description="关闭后死叉只平多、不做空")

    @model_validator(mode="after")
    def _check(self):
        if self.fast >= self.slow:
            raise ValueError("快线周期必须小于慢线周期")
        return self


@register
class MACDFutures(Strategy):
    id = "macd_futures"
    name = "MACD 期货多空"
    category = "futures"
    style = "趋势跟踪"
    summary = "DIF 上穿 DEA（金叉）做多、下穿（死叉）做空，可加零轴过滤只顺着大趋势方向开仓，是 MACD 在可做空市场上的完整用法。"
    aliases = ("MACD期货", "期货MACD", "MACD多空", "MACD 期货")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        dif, dea, hist = macd(bars.close, p.fast, p.slow, p.signal)
        golden, dead = dif > dea, dif < dea
        long_in = golden & (dif > 0) if p.zero_filter else golden
        short_in = dead & (dif < 0) if p.zero_filter else dead
        pos = state_machine(long_in, dead, short_in if p.allow_short else None, golden)
        pos = apply_stops(pos, bars.close, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pos * p.position_limit, indicators={"DIF": dif, "DEA": dea, "MACD 柱": hist})
