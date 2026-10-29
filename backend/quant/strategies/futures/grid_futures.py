from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import grid_position
from ..indicators import sma


class Params(StrategyParams):
    base_window: int = Field(60, ge=5, le=250, title="基准价均线周期", description="网格中心价取该周期均线")
    step: float = Field(0.02, ge=0.005, le=0.2, title="网格间距", description="相邻两格的价格间距（比例）")
    levels: int = Field(5, ge=1, le=20, title="网格档数", description="中心价单侧的格数，走满所有格时仓位最大")
    position_limit: float = Field(0.2, gt=0, le=1, title="单品种仓位上限",
                                  description="单个品种满档时名义市值占权益的比例")
    allow_short: bool = Field(True, title="允许做空",
                              description="开启后价格高于中心价时逐格做空；关闭后只在中心价下方逐格做多")


@register
class GridFutures(Strategy):
    id = "grid_futures"
    name = "网格期货策略"
    category = "futures"
    style = "震荡套利"
    summary = "以均线为中心双向布网，价格每下跌一格加一档多单、每上涨一格加一档空单，在震荡中反复低买高卖。"
    aliases = ("网格期货", "期货网格", "双向网格")
    Params = Params
    default_universe = "M,Y,P,SR,CF,TA,MA"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        base = sma(bars.close, p.base_window)
        pos = grid_position(bars.close, base, p.step, p.levels, allow_short=p.allow_short)
        lines = {"中心价": base, "上方满档": base * (1 + p.levels * p.step),
                 "下方满档": base * (1 - p.levels * p.step)}
        return StrategyOutput(weights=pos * p.position_limit, indicators=lines)
