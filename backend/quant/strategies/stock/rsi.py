from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, pool_weights, state_machine
from ..indicators import cross_up, rsi


class Params(StopParams):
    period: int = Field(14, ge=2, le=60, title="RSI 周期", description="计算平均涨跌幅的天数，越短越灵敏")
    oversold: float = Field(30, ge=5, le=50, title="超卖阈值", description="RSI 从下方上穿该值时买入")
    overbought: float = Field(70, ge=50, le=95, title="超买阈值", description="RSI 高于该值时卖出")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")

    @model_validator(mode="after")
    def _check(self):
        if self.oversold >= self.overbought:
            raise ValueError("超卖阈值必须小于超买阈值")
        return self


@register
class RSIStock(Strategy):
    id = "rsi_stock"
    name = "RSI 超买超卖"
    category = "stock"
    style = "均值回归"
    summary = "RSI 从超卖区回升时买入，进入超买区时卖出，捕捉超跌反弹。"
    aliases = ("RSI", "相对强弱", "超买超卖", "RSI策略")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})

    def generate(self, bars):
        p = self.params
        r = rsi(bars.close, p.period)
        level = r * 0 + p.oversold
        pos = state_machine(cross_up(r, level), r > p.overbought)
        pos = apply_stops(pos, bars.close, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pool_weights(pos, p.position_ratio), indicators={"RSI": r})
