from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, state_machine
from ..indicators import rsi, sma


class Params(StopParams):
    trend_ma: int = Field(200, ge=50, le=300, title="趋势均线周期",
                          description="收盘价在该均线之上只做多、之下只做空，原版取 200 日")
    rsi_period: int = Field(2, ge=2, le=14, title="RSI 周期", description="极短周期的 RSI 用来识别短期回调，原版取 2")
    oversold: float = Field(10, ge=1, le=40, title="超卖阈值", description="上升趋势中 RSI 低于该值视为回调到位，做多")
    overbought: float = Field(90, ge=60, le=99, title="超买阈值", description="下降趋势中 RSI 高于该值视为反弹到位，做空")
    exit_ma: int = Field(5, ge=2, le=30, title="离场均线周期",
                         description="多头收盘站上该均线、空头收盘跌破该均线时离场，原版取 5 日")
    position_limit: float = Field(0.1, gt=0, le=1, title="单品种仓位上限", description="单个品种名义市值占权益的比例")
    allow_short: bool = Field(True, title="允许做空", description="关闭后只在上升趋势中做多回调")

    @model_validator(mode="after")
    def _check(self):
        if self.oversold >= self.overbought:
            raise ValueError("超卖阈值必须低于超买阈值")
        if self.exit_ma >= self.trend_ma:
            raise ValueError("离场均线周期必须小于趋势均线周期")
        return self


@register
class RSI2PullbackFutures(Strategy):
    id = "rsi2_pullback_futures"
    name = "RSI(2) 趋势回调"
    category = "futures"
    style = "趋势回调（顺大势逆小势）"
    summary = "先用 200 日均线定大方向，再用 2 日 RSI 找短期回调：上升趋势中 RSI(2) 跌破 10 做多、下降趋势中升破 90 做空，价格越过 5 日均线就离场。"
    aliases = ("RSI2", "RSI(2)", "康纳斯", "Connors", "趋势回调", "回调买入", "RSI2回调")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        trend, fast_exit = sma(c, p.trend_ma), sma(c, p.exit_ma)
        r = rsi(c, p.rsi_period)
        up, down = c > trend, c < trend
        pos = state_machine(up & (r < p.oversold), c > fast_exit,
                            (down & (r > p.overbought)) if p.allow_short else None, c < fast_exit)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pos * p.position_limit,
                              indicators={f"MA{p.trend_ma}": trend, f"MA{p.exit_ma}": fast_exit, f"RSI({p.rsi_period})": r})
