from pydantic import Field

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, pool_weights, state_machine
from ..indicators import cross_down, cross_up, kdj


class Params(StopParams):
    n: int = Field(9, ge=3, le=60, title="RSV 周期 N", description="计算未成熟随机值 RSV 的天数")
    m1: int = Field(3, ge=1, le=10, title="K 平滑周期", description="RSV 平滑得到 K 的周期")
    m2: int = Field(3, ge=1, le=10, title="D 平滑周期", description="K 平滑得到 D 的周期")
    buy_level: float = Field(30, ge=0, le=60, title="低位金叉阈值", description="只在 K 低于该值时接受金叉买入")
    sell_level: float = Field(70, ge=40, le=100, title="高位死叉阈值",
                              description="K 高于该值出现死叉时卖出")
    exit_any_cross: bool = Field(True, title="任意死叉离场",
                                 description="开启后任何位置的死叉都卖出；关闭后只在高位死叉卖出，持仓更久")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")


@register
class KDJStock(Strategy):
    id = "kdj_stock"
    name = "KDJ 策略"
    category = "stock"
    style = "震荡指标"
    summary = "K 线在低位上穿 D 线时买入，高位下穿时卖出，适合区间震荡行情。"
    aliases = ("KDJ", "随机指标", "KDJ金叉")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})

    def generate(self, bars):
        p = self.params
        k, d, j = kdj(bars.high, bars.low, bars.close, p.n, p.m1, p.m2)
        entry = cross_up(k, d) & (k < p.buy_level)
        dead = cross_down(k, d)
        exit_ = dead if p.exit_any_cross else dead & (k > p.sell_level)
        pos = state_machine(entry, exit_)
        pos = apply_stops(pos, bars.close, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pool_weights(pos, p.position_ratio),
                              indicators={"K": k, "D": d, "J": j})
