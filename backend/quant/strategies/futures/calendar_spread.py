import numpy as np
from pydantic import Field, model_validator

from ...data.catalog import NEXT_LEG_SUFFIX
from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import state_machine


class Params(StrategyParams):
    window: int = Field(20, ge=5, le=120, title="价差均值窗口", description="估计价差正常水平的天数")
    entry_z: float = Field(2.0, gt=0, le=5, title="开仓 Z 值", description="价差偏离均值超过几个标准差时开仓")
    exit_z: float = Field(0.5, ge=0, le=3, title="平仓 Z 值", description="价差回到均值附近几个标准差内时平仓")
    leg_weight: float = Field(0.2, gt=0, le=1, title="单腿仓位",
                              description="每条腿的名义市值占权益比例，两腿方向相反、金额相等")

    @model_validator(mode="after")
    def _check(self):
        if self.exit_z >= self.entry_z:
            raise ValueError("平仓 Z 值必须小于开仓 Z 值")
        return self


@register
class CalendarSpreadFutures(Strategy):
    id = "calendar_spread_futures"
    name = "跨期简单套利"
    category = "futures"
    style = "统计套利"
    summary = "同一品种主力与次主力合约的价差偏离历史均值时，做空偏贵的一腿、做多偏便宜的一腿，等价差回归后平仓。"
    aliases = ("跨期套利", "跨期价差", "跨期简单套利", "期现价差", "价差套利")
    Params = Params
    default_universe = "RB,HC,M,TA,MA"
    asset_types = frozenset({"futures"})
    min_symbols = 2

    @classmethod
    def expand_universe(cls, symbols):
        out = []
        for s in symbols:
            base = s.removesuffix(NEXT_LEG_SUFFIX)
            for leg in (base, base + NEXT_LEG_SUFFIX):
                if leg not in out:
                    out.append(leg)
        return out

    def generate(self, bars):
        p = self.params
        bases = [s for s in bars.symbols if not s.endswith(NEXT_LEG_SUFFIX)]
        w = bars.close * 0.0
        indicators = {"价差Z值": w.copy(), "对数价差": w.copy()}
        for b in bases:
            far = b + NEXT_LEG_SUFFIX
            if far not in bars.symbols:
                continue
            # 价差用两腿当日的真实价格计算（同一天、不需要复权）
            spread = np.log(bars.mark_close[far] / bars.mark_close[b]).where(
                bars.tradable[b] & bars.tradable[far])
            # 任一腿换月后价差的含义变了，按换月切分成段，每段单独计算均值和标准差
            seg = (bars.roll[b] | bars.roll[far]).cumsum()
            g = spread.groupby(seg)
            mean = g.transform(lambda s: s.rolling(p.window, min_periods=p.window).mean())
            sd = g.transform(lambda s: s.rolling(p.window, min_periods=p.window).std(ddof=0))
            z = ((spread - mean) / sd.replace(0, np.nan)).to_frame("z")
            # 价差偏高（远月相对贵）→ 卖远买近，记为 −1；偏低 → 买远卖近，记为 +1
            pos = state_machine(z < -p.entry_z, (z > -p.exit_z) | z.isna(),
                                z > p.entry_z, (z < p.exit_z) | z.isna())["z"]
            w[far] = pos * p.leg_weight
            w[b] = -pos * p.leg_weight
            indicators["价差Z值"][b] = z["z"]
            indicators["对数价差"][b] = spread
        return StrategyOutput(
            weights=w, indicators=indicators,
            notes=["换月后需要重新积累价差样本，期间不开新仓；已有持仓在新一段价差出来前会平掉。"],
        )
