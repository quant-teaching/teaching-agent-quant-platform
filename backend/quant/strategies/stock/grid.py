from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import grid_position, pool_weights
from ..indicators import sma


class Params(StrategyParams):
    base_window: int = Field(60, ge=5, le=250, title="基准价均线周期",
                             description="网格中心价取该周期均线，随行情缓慢移动")
    step: float = Field(0.03, ge=0.005, le=0.2, title="网格间距",
                        description="相邻两格的价格间距（比例），越小交易越频繁")
    levels: int = Field(5, ge=1, le=20, title="网格档数", description="中心价下方的格数，跌满所有格时满仓")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")


@register
class GridStock(Strategy):
    id = "grid_stock"
    name = "网格交易"
    category = "stock"
    style = "震荡套利"
    summary = "以均线为中心划出等距价格格子，价格每下跌一格加仓一档、每上涨一格减仓一档，低买高卖。"
    aliases = ("网格", "网格交易", "网格股票")
    Params = Params
    default_universe = "600036,601398,600900,601088,600028"
    asset_types = frozenset({"stock", "industry"})

    def generate(self, bars):
        p = self.params
        base = sma(bars.close, p.base_window)
        pos = grid_position(bars.close, base, p.step, p.levels, allow_short=False)
        lines = {"中心价": base}
        for k in (1, p.levels):
            lines[f"下方第{k}格"] = base * (1 - k * p.step)
        return StrategyOutput(weights=pool_weights(pos, p.position_ratio), indicators=lines)
