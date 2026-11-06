from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, pool_weights, state_machine
from ..indicators import bias, sma


class Params(StopParams):
    window: int = Field(20, ge=5, le=120, title="均线周期", description="乖离率以这条均线为'正常价格'")
    entry_bias: float = Field(0.08, gt=0, le=0.5, title="买入乖离",
                              description="收盘价低于均线超过该比例（乖离率 < −该值）时买入，押注超跌反弹")
    exit_bias: float = Field(0.0, ge=-0.2, le=0.5, title="卖出乖离",
                             description="乖离率回升到该值以上时卖出，0 表示回到均线就离场")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")

    @model_validator(mode="after")
    def _check(self):
        if self.exit_bias <= -self.entry_bias:
            raise ValueError("卖出乖离必须大于 −买入乖离，否则刚买入就会触发卖出")
        return self


@register
class BiasStock(Strategy):
    id = "bias_stock"
    name = "乖离率回归"
    category = "stock"
    style = "均值回归"
    summary = "股价跌得离均线太远（乖离率过低）时买入，等价格回到均线附近卖出，赚超跌反弹的钱。"
    aliases = ("乖离率", "BIAS", "均线偏离", "超跌反弹", "乖离率策略")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        b = bias(c, p.window)
        pos = state_machine(b < -p.entry_bias, b > p.exit_bias)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pool_weights(pos, p.position_ratio),
                              indicators={f"MA{p.window}": sma(c, p.window), "乖离率": b})
