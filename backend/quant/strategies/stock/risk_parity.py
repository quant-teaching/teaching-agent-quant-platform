from typing import Literal

import numpy as np
from pydantic import Field

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, weighted_on_mask
from ..indicators import realized_vol


class Params(StrategyParams):
    vol_window: int = Field(60, ge=10, le=250, title="波动率窗口", description="估计各资产波动率的天数")
    rebalance: Literal["W", "M", "Q"] = Field("M", title="调仓频率", description="W 每周、M 每月、Q 每季度")
    max_weight: float = Field(0.25, gt=0, le=1, title="单资产权重上限", description="防止低波动资产权重过度集中")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例", description="满仓时占总资金的比例")


@register
class RiskParityStock(Strategy):
    id = "risk_parity_stock"
    name = "简易风险平价"
    category = "stock"
    style = "资产配置"
    summary = "按波动率倒数分配权重，让每个资产贡献大致相同的风险，而不是相同的资金。"
    aliases = ("风险平价", "简易风险平价", "波动率倒数加权", "risk parity")
    Params = Params
    default_universe = "industries"
    asset_types = frozenset({"stock", "industry"})
    min_symbols = 2

    def generate(self, bars):
        p = self.params
        vol = realized_vol(bars.close, p.vol_window).where(bars.tradable)
        inv = 1 / vol.replace(0, np.nan)
        raw = inv.div(inv.sum(axis=1), axis=0)
        # 截断上限后把多出的权重按比例分给其他资产，迭代几次即可收敛
        for _ in range(10):
            over = raw > p.max_weight
            if not over.any().any():
                break
            excess = (raw - p.max_weight).clip(lower=0).sum(axis=1)
            raw = raw.clip(upper=p.max_weight)
            free = raw.where(~over)
            raw = raw + free.div(free.sum(axis=1), axis=0).mul(excess, axis=0).fillna(0)
        raw = raw.clip(upper=p.max_weight) * p.position_ratio
        mask = rebalance_mask(bars.dates, p.rebalance)
        w = weighted_on_mask(raw, mask)
        return StrategyOutput(weights=w, rebalance=mask, indicators={"年化波动率": vol, "目标权重": raw})
