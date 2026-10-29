from typing import Literal

from pydantic import Field

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, pool_weights, state_machine
from ..indicators import bollinger


class Params(StopParams):
    window: int = Field(20, ge=5, le=120, title="均线周期 N", description="中轨均线和标准差的计算天数")
    num_std: float = Field(2.0, ge=0.5, le=4, title="标准差倍数",
                           description="上下轨距离中轨几个标准差，越大通道越宽、信号越少")
    mode: Literal["breakout", "reversion"] = Field(
        "breakout", title="交易模式",
        description="breakout 突破：收盘站上上轨买入、跌破中轨卖出（趋势思路）；"
                    "reversion 回归：跌破下轨买入、回到中轨卖出（均值回归思路）",
    )
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")


@register
class BollingerStock(Strategy):
    id = "bollinger_stock"
    name = "布林带交易"
    category = "stock"
    style = "趋势跟踪 / 均值回归"
    summary = "以均线 ± 若干倍标准差构成价格通道，突破上轨视为走强买入，跌破中轨离场。"
    aliases = ("布林带", "布林线", "BOLL", "布林带股票")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        mid, up, lo = bollinger(c, p.window, p.num_std)
        if p.mode == "breakout":
            pos = state_machine(c > up, c < mid)
        else:
            pos = state_machine(c < lo, c > mid)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pool_weights(pos, p.position_ratio),
                              indicators={"上轨": up, "中轨": mid, "下轨": lo})
