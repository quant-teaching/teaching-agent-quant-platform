from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, pool_weights, state_machine
from ..indicators import cci


class Params(StopParams):
    window: int = Field(20, ge=5, le=120, title="计算周期", description="典型价均值和平均绝对偏差的天数")
    entry_level: float = Field(100, ge=0, le=300, title="入场线",
                               description="CCI 升破该值说明价格异常强势、可能进入趋势，买入（经典取 +100）")
    exit_level: float = Field(0, ge=-300, le=200, title="离场线", description="CCI 跌回该值以下卖出")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")

    @model_validator(mode="after")
    def _check(self):
        if self.exit_level >= self.entry_level:
            raise ValueError("离场线必须低于入场线")
        return self


@register
class CCIStock(Strategy):
    id = "cci_stock"
    name = "CCI 顺势指标"
    category = "stock"
    style = "趋势跟踪（震荡指标）"
    summary = "CCI 衡量价格偏离统计均值的程度，升破 +100 视为进入强势区间买入，跌回 0 以下卖出。"
    aliases = ("CCI", "顺势指标", "商品通道指数", "CCI策略")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        x = cci(bars.high, bars.low, c, p.window)
        pos = state_machine(x > p.entry_level, x < p.exit_level)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pool_weights(pos, p.position_ratio), indicators={"CCI": x})
