from typing import Literal

import numpy as np
from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, weighted_on_mask
from ..indicators import momentum, realized_vol


class Params(StrategyParams):
    lookbacks: str = Field("20,60,120", title="动量回看期组合",
                           description="逗号分隔的多个回看天数，信号取各周期涨跌方向的平均，多周期更稳健")
    vol_window: int = Field(60, ge=10, le=250, title="波动率窗口", description="估计品种波动率的天数")
    target_vol: float = Field(0.03, gt=0, le=0.5, title="单品种目标波动率",
                              description="按波动率倒数调整仓位，使每个品种贡献的年化波动约等于该值")
    position_limit: float = Field(0.3, gt=0, le=1, title="单品种仓位上限",
                                  description="单个品种名义市值占权益比例的上限，防止低波动品种杠杆过高")
    rebalance: Literal["W", "M"] = Field("W", title="调仓频率", description="W 每周、M 每月")


@register
class TrendCTAFutures(Strategy):
    id = "trend_cta_futures"
    name = "趋势跟踪 CTA"
    category = "futures"
    style = "时间序列动量"
    summary = "根据各品种过去多个周期的涨跌方向决定多空，并按波动率倒数分配仓位，是管理期货基金最主流的配置方式。"
    aliases = ("趋势跟踪", "CTA", "趋势CTA", "时间序列动量", "TSMOM", "趋势跟踪CTA")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        try:
            lbs = [int(x) for x in p.lookbacks.replace("，", ",").split(",") if x.strip()]
        except ValueError as e:
            raise ValueError("动量回看期组合应为逗号分隔的整数，例如 20,60,120") from e
        c = bars.close
        signal = sum(np.sign(momentum(c, n)) for n in lbs) / len(lbs)
        vol = realized_vol(c, p.vol_window)
        size = (p.target_vol / vol.replace(0, np.nan)).clip(upper=p.position_limit)
        raw = (signal * size).where(bars.tradable)
        mask = rebalance_mask(bars.dates, p.rebalance)
        return StrategyOutput(weights=weighted_on_mask(raw, mask), rebalance=mask,
                              indicators={"趋势信号": signal, "年化波动率": vol})
