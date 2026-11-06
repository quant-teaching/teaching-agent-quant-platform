from typing import Literal

import numpy as np
import pandas as pd
from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, weighted_on_mask


class Params(StrategyParams):
    target_vol: float = Field(0.15, gt=0, le=0.6, title="目标年化波动率",
                              description="希望组合长期保持的年化波动率，实际波动越高仓位越低")
    vol_window: int = Field(20, ge=5, le=120, title="波动率窗口",
                            description="估计近期波动率的天数，越短对风险变化反应越快、仓位调整也越频繁")
    max_position: float = Field(1.0, gt=0, le=1, title="最高仓位", description="仓位上限，股票不加杠杆所以最多 1")
    min_position: float = Field(0.0, ge=0, le=1, title="最低仓位", description="波动再大也至少保留的仓位")
    rebalance: Literal["W", "M"] = Field("W", title="调仓频率", description="W 每周、M 每月")


@register
class VolTargetStock(Strategy):
    id = "vol_target_stock"
    name = "目标波动率择时"
    category = "stock"
    style = "波动率策略（风险控制）"
    summary = "等权持有股票池，按'目标波动率 ÷ 近期实际波动率'调整总仓位：市场越动荡仓位越低，平静时恢复满仓。"
    aliases = ("目标波动率", "波动率择时", "波动率控制", "风险预算", "volatility targeting")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})
    min_symbols = 2

    def generate(self, bars):
        p = self.params
        if p.min_position > p.max_position:
            raise ValueError("最低仓位不能高于最高仓位")
        r = bars.returns()
        pool_ret = r.mean(axis=1)  # 等权组合的日收益
        vol = pool_ret.rolling(p.vol_window, min_periods=p.vol_window).std() * np.sqrt(252)
        exposure = (p.target_vol / vol.replace(0, np.nan)).clip(p.min_position, p.max_position)
        live = bars.tradable.astype(float)
        raw = live.div(live.sum(axis=1).replace(0, np.nan), axis=0).mul(exposure, axis=0)
        mask = rebalance_mask(bars.dates, p.rebalance)
        wide = lambda x: pd.DataFrame({sym: x for sym in bars.symbols})  # noqa: E731
        return StrategyOutput(weights=weighted_on_mask(raw, mask), rebalance=mask,
                              indicators={"目标仓位": wide(exposure), "组合年化波动率": wide(vol)})
