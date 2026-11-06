from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, pool_weights, state_machine
from ..indicators import cross_up, sma, williams_r


class Params(StopParams):
    window: int = Field(14, ge=5, le=60, title="计算周期", description="%R 用过去 N 日的最高价和最低价计算")
    oversold: float = Field(-80, ge=-99, le=-50, title="超卖线", description="%R 从该线下方回升上穿时买入")
    overbought: float = Field(-20, ge=-50, le=-1, title="超买线", description="%R 升到该线上方时卖出")
    trend_ma: int = Field(0, ge=0, le=250, title="趋势过滤均线",
                          description="只在收盘价高于该均线时买入，避免在下跌趋势里抄底，0 表示不过滤")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")

    @model_validator(mode="after")
    def _check(self):
        if self.oversold >= self.overbought:
            raise ValueError("超卖线必须低于超买线")
        return self


@register
class WilliamsStock(Strategy):
    id = "williams_stock"
    name = "威廉指标 %R"
    category = "stock"
    style = "震荡指标（超买超卖）"
    summary = "%R 衡量收盘价在近 N 日高低区间中的位置，从超卖区回升时买入、进入超买区时卖出。"
    aliases = ("威廉指标", "威廉", "WR", "%R", "威廉%R", "williams")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        wr = williams_r(bars.high, bars.low, c, p.window)
        level = wr * 0 + p.oversold
        entry = cross_up(wr, level)
        if p.trend_ma:
            entry &= c > sma(c, p.trend_ma)
        pos = state_machine(entry, wr > p.overbought)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pool_weights(pos, p.position_ratio), indicators={"%R": wr})
