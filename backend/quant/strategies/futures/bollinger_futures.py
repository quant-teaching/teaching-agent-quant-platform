from pydantic import Field

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, state_machine
from ..indicators import bollinger


class Params(StopParams):
    window: int = Field(20, ge=5, le=120, title="均线周期 N", description="中轨均线和标准差的计算天数")
    num_std: float = Field(2.0, ge=0.5, le=4, title="标准差倍数", description="上下轨距离中轨几个标准差")
    position_limit: float = Field(0.2, gt=0, le=1, title="单品种仓位上限",
                                  description="单个品种名义市值占权益的比例")
    allow_short: bool = Field(True, title="允许做空", description="关闭后只做多头突破")


@register
class BollingerFutures(Strategy):
    id = "bollinger_futures"
    name = "布林带期货策略"
    category = "futures"
    style = "趋势跟踪（通道突破）"
    summary = "收盘突破布林带上轨做多、跌破下轨做空，回到中轨平仓，多空双向捕捉波动率扩张。"
    aliases = ("布林带期货", "期货布林带", "布林带突破")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        mid, up, lo = bollinger(c, p.window, p.num_std)
        pos = state_machine(c > up, c < mid, (c < lo) if p.allow_short else None, c > mid)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pos * p.position_limit, indicators={"上轨": up, "中轨": mid, "下轨": lo})
