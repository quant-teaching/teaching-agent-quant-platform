from typing import Literal

from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, pool_weights, state_machine
from ..indicators import cross_down, cross_up, ema, sma


class Params(StopParams):
    fast: int = Field(10, ge=2, le=120, title="短均线周期", description="短期均线天数，越短对价格变化越敏感")
    slow: int = Field(30, ge=5, le=250, title="长均线周期", description="长期均线天数，代表中期趋势方向")
    ma_type: Literal["SMA", "EMA"] = Field("SMA", title="均线类型",
                                            description="SMA 简单平均；EMA 指数平均，对近期价格权重更大、反应更快")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")

    @model_validator(mode="after")
    def _check(self):
        if self.fast >= self.slow:
            raise ValueError("短均线周期必须小于长均线周期")
        return self


@register
class DualMAStock(Strategy):
    id = "dual_ma_stock"
    name = "双均线策略"
    category = "stock"
    style = "趋势跟踪"
    summary = "短均线上穿长均线（金叉）买入，下穿（死叉）卖出，是最经典的趋势跟踪入门策略。"
    aliases = ("双均线", "均线交叉", "金叉死叉", "双均线股票")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})

    def generate(self, bars):
        p = self.params
        ma = sma if p.ma_type == "SMA" else ema
        fast, slow = ma(bars.close, p.fast), ma(bars.close, p.slow)
        # 金叉后持有、死叉后空仓，等价于"短均线在长均线之上时持有"
        pos = state_machine(cross_up(fast, slow) | (fast > slow), cross_down(fast, slow))
        pos = apply_stops(pos, bars.close, p.stop_loss, p.take_profit)
        return StrategyOutput(
            weights=pool_weights(pos, p.position_ratio),
            indicators={f"MA{p.fast}": fast, f"MA{p.slow}": slow},
        )
