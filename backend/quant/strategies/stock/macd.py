from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, pool_weights, state_machine
from ..indicators import cross_down, cross_up, macd


class Params(StopParams):
    fast: int = Field(12, ge=2, le=60, title="快线周期", description="快速 EMA 天数")
    slow: int = Field(26, ge=5, le=120, title="慢线周期", description="慢速 EMA 天数")
    signal: int = Field(9, ge=2, le=30, title="信号线周期", description="DIF 的 EMA 平滑天数，得到 DEA")
    zero_filter: bool = Field(False, title="零轴过滤",
                              description="开启后只在 DIF 位于零轴上方（中期趋势向上）时接受金叉买入")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")

    @model_validator(mode="after")
    def _check(self):
        if self.fast >= self.slow:
            raise ValueError("快线周期必须小于慢线周期")
        return self


@register
class MACDStock(Strategy):
    id = "macd_stock"
    name = "MACD 交易策略"
    category = "stock"
    style = "趋势跟踪"
    summary = "DIF 上穿 DEA（MACD 金叉）买入，下穿（死叉）卖出，利用均线收敛发散判断趋势。"
    aliases = ("MACD", "MACD金叉死叉", "移动平均收敛发散", "指数平滑异同平均线")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})

    def generate(self, bars):
        p = self.params
        dif, dea, hist = macd(bars.close, p.fast, p.slow, p.signal)
        entry = cross_up(dif, dea)
        if p.zero_filter:
            entry &= dif > 0
        pos = state_machine(entry, cross_down(dif, dea))
        pos = apply_stops(pos, bars.close, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pool_weights(pos, p.position_ratio),
                              indicators={"DIF": dif, "DEA": dea, "MACD柱": hist})
