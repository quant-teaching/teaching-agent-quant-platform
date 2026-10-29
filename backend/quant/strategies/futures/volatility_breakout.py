import numpy as np
from pydantic import Field

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, state_machine


class Params(StopParams):
    n: int = Field(4, ge=1, le=30, title="波幅回看天数", description="计算参考波幅 Range 的天数")
    k_up: float = Field(0.5, gt=0, le=3, title="上轨系数 K1", description="上轨 = 当日开盘价 + K1 × Range")
    k_down: float = Field(0.5, gt=0, le=3, title="下轨系数 K2", description="下轨 = 当日开盘价 − K2 × Range")
    position_limit: float = Field(0.2, gt=0, le=1, title="单品种仓位上限",
                                  description="单个品种名义市值占权益的比例")
    allow_short: bool = Field(True, title="允许做空", description="关闭后只做多")


@register
class VolatilityBreakoutFutures(Strategy):
    id = "volatility_breakout_futures"
    name = "波动率突破"
    category = "futures"
    style = "波动率突破（Dual Thrust）"
    summary = "以近几日波幅设定当日上下轨，收盘突破上轨做多、跌破下轨做空，持仓直到出现反向突破。"
    aliases = ("波动率突破", "Dual Thrust", "DualThrust", "波幅突破", "波动率策略")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        o, h, lo, c = bars.open, bars.high, bars.low, bars.close
        hh = h.rolling(p.n).max().shift()
        ll = lo.rolling(p.n).min().shift()
        hc = c.rolling(p.n).max().shift()
        lc = c.rolling(p.n).min().shift()
        rng = np.maximum(hh - lc, hc - ll)
        up, dn = o + p.k_up * rng, o - p.k_down * rng
        # 日线版本：收盘价确认突破，次日开盘成交；出现反向突破时反手（多空停止反转）
        pos = state_machine(c > up, c < dn, (c < dn) if p.allow_short else None, c > up)
        pos = apply_stops(pos, c, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pos * p.position_limit, indicators={"上轨": up, "下轨": dn})
