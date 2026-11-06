from pydantic import Field

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, pool_weights, state_machine
from ..indicators import obv, sma


class Params(StopParams):
    obv_ma: int = Field(30, ge=5, le=120, title="OBV 均线周期", description="OBV 高于自身均线说明资金在持续流入")
    price_ma: int = Field(30, ge=5, le=250, title="价格均线周期", description="同时要求价格在均线之上，量价配合才买入")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")


@register
class OBVStock(Strategy):
    id = "obv_stock"
    name = "OBV 能量潮"
    category = "stock"
    style = "量价分析"
    summary = "把成交量按涨跌方向累加成能量潮 OBV，OBV 与价格同时站上各自均线（量价齐升）时买入，OBV 跌破均线时卖出。"
    aliases = ("OBV", "能量潮", "量价", "成交量策略", "OBV能量潮")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        o = obv(c, bars.volume)
        o_ma, c_ma = sma(o, p.obv_ma), sma(c, p.price_ma)
        pos = state_machine((o > o_ma) & (c > c_ma), o < o_ma)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pool_weights(pos, p.position_ratio),
                              indicators={"OBV": o, "OBV 均线": o_ma, f"MA{p.price_ma}": c_ma})
