from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, pool_weights, state_machine
from ..indicators import sma


class Params(StopParams):
    fast: int = Field(5, ge=2, le=60, title="短均线周期", description="最灵敏的一条均线，代表最近一周左右的方向")
    mid: int = Field(20, ge=5, le=120, title="中均线周期", description="代表一个月左右的方向，也是离场判断线")
    slow: int = Field(60, ge=10, le=250, title="长均线周期", description="代表一个季度左右的大方向，用来过滤逆势信号")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")

    @model_validator(mode="after")
    def _check(self):
        if not self.fast < self.mid < self.slow:
            raise ValueError("需要满足：短均线周期 < 中均线周期 < 长均线周期")
        return self


@register
class TripleMAStock(Strategy):
    id = "triple_ma_stock"
    name = "三均线多头排列"
    category = "stock"
    style = "趋势跟踪"
    summary = "短、中、长三条均线自上而下依次排列（多头排列）时买入，短均线跌破中均线时卖出，比双均线多一道大趋势过滤。"
    aliases = ("三均线", "多头排列", "均线排列", "三均线策略")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        f, m, s = sma(c, p.fast), sma(c, p.mid), sma(c, p.slow)
        # 进场要求三线多头排列；离场只看短线是否跌破中线，不必等到长线拐头
        pos = state_machine((f > m) & (m > s), f < m)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pool_weights(pos, p.position_ratio),
                              indicators={f"MA{p.fast}": f, f"MA{p.mid}": m, f"MA{p.slow}": s})
