from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import state_machine
from ..indicators import sma, zscore


class Params(StrategyParams):
    window: int = Field(20, ge=5, le=120, title="均值窗口", description="计算价格均值和标准差的天数")
    entry_z: float = Field(2.0, gt=0, le=5, title="开仓 Z 值",
                           description="价格高于均值几个标准差做空、低于做多")
    exit_z: float = Field(0.5, ge=0, le=3, title="平仓 Z 值", description="价格回到均值几个标准差以内平仓")
    stop_z: float = Field(4.0, gt=0, le=10, title="止损 Z 值",
                          description="偏离继续扩大到几个标准差时认输止损（说明可能出现了趋势）")
    position_limit: float = Field(0.15, gt=0, le=1, title="单品种仓位上限",
                                  description="单个品种名义市值占权益的比例")

    @model_validator(mode="after")
    def _check(self):
        if not self.exit_z < self.entry_z < self.stop_z:
            raise ValueError("需要满足：平仓 Z 值 < 开仓 Z 值 < 止损 Z 值")
        return self


@register
class MeanReversionFutures(Strategy):
    id = "mean_reversion_futures"
    name = "均值回归"
    category = "futures"
    style = "均值回归"
    summary = "价格大幅偏离近期均值时反向开仓，押注价格回归均值；偏离继续扩大则止损。"
    aliases = ("均值回归", "均值回复", "Z值回归", "均值回归期货")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        c = bars.close
        z = zscore(c, p.window)
        pos = state_machine(
            (z < -p.entry_z) & (z > -p.stop_z), (z > -p.exit_z) | (z < -p.stop_z),
            (z > p.entry_z) & (z < p.stop_z), (z < p.exit_z) | (z > p.stop_z),
        )
        return StrategyOutput(weights=pos * p.position_limit, indicators={"均线": sma(c, p.window), "Z值": z})
