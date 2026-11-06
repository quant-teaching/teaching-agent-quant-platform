from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, pool_weights, state_machine
from ..indicators import donchian


class Params(StopParams):
    entry_window: int = Field(20, ge=5, le=250, title="突破周期",
                              description="收盘价创过去 N 日（不含当日）最高价时买入，N 越大越只抓大级别趋势")
    exit_window: int = Field(10, ge=3, le=120, title="离场周期",
                             description="收盘价跌破过去 M 日最低价时卖出，应小于突破周期")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")

    @model_validator(mode="after")
    def _check(self):
        if self.exit_window >= self.entry_window:
            raise ValueError("离场周期应小于突破周期")
        return self


@register
class DonchianStock(Strategy):
    id = "donchian_stock"
    name = "唐奇安通道突破"
    category = "stock"
    style = "趋势跟踪（通道突破）"
    summary = "收盘价创 N 日新高买入、跌破 M 日新低卖出，是海龟交易法则的股票简化版（只做多、不加仓）。"
    aliases = ("唐奇安", "唐奇安通道", "通道突破", "新高突破", "donchian", "唐奇安股票")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        up, _ = donchian(bars.high, bars.low, p.entry_window)
        _, lo = donchian(bars.high, bars.low, p.exit_window)
        pos = state_machine(c > up, c < lo)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pool_weights(pos, p.position_ratio),
                              indicators={f"{p.entry_window}日高点": up, f"{p.exit_window}日低点": lo})
