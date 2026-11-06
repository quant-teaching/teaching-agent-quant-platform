from pydantic import Field

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, pool_weights, state_machine
from ..indicators import cross_down, cross_up, sma, trix


class Params(StopParams):
    n: int = Field(12, ge=3, le=60, title="平滑周期 N", description="三次指数平滑各自使用的天数，常用 12")
    m: int = Field(9, ge=2, le=60, title="信号线周期 M", description="TRIX 的简单均线 MATRIX 的天数，常用 9")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")


@register
class TRIXStock(Strategy):
    id = "trix_stock"
    name = "TRIX 三重指数平滑"
    category = "stock"
    style = "趋势跟踪"
    summary = "对收盘价连续做三次指数平滑后取变化率得到 TRIX，滤掉短期噪音；TRIX 上穿其均线 MATRIX 买入、下穿卖出，适合中长线趋势。"
    aliases = ("TRIX", "三重指数平滑", "TRIX指标", "三重指数平滑均线")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        t = trix(c, p.n)
        ma = sma(t, p.m)
        pos = state_machine(cross_up(t, ma) | (t > ma), cross_down(t, ma))
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pool_weights(pos, p.position_ratio), indicators={"TRIX": t, "MATRIX": ma})
