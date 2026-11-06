from typing import Literal

import numpy as np
import pandas as pd
from pydantic import Field

from ...data.catalog import NEXT_LEG_SUFFIX
from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, top_k_weights


class Params(StrategyParams):
    top_k: int = Field(3, ge=1, le=8, title="每边品种数", description="做多展期收益最高的 K 个、做空最低的 K 个")
    smooth: int = Field(5, ge=1, le=60, title="平滑天数", description="展期收益取最近若干天的平均，减少单日价格噪音")
    position_limit: float = Field(0.1, gt=0, le=0.5, title="单品种仓位", description="每个入选品种名义市值占权益的比例")
    rebalance: Literal["W", "M"] = Field("M", title="调仓频率", description="W 每周、M 每月")


@register
class CarryFutures(Strategy):
    id = "carry_futures"
    name = "期限结构展期收益"
    category = "futures"
    style = "期限结构（Carry）"
    summary = "比较主力和次主力合约价格：近月比远月贵（贴水/backwardation）的品种做多，近月更便宜（升水/contango）的做空，赚取合约临近到期时向现货收敛的展期收益。"
    aliases = ("展期收益", "期限结构", "carry", "Carry", "升贴水", "基差动量", "期限结构套利")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})
    min_symbols = 4

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
        bases = [s for s in bars.symbols if not s.endswith(NEXT_LEG_SUFFIX) and s + NEXT_LEG_SUFFIX in bars.symbols]
        carry = pd.DataFrame(np.nan, index=bars.dates, columns=bars.symbols)
        for b in bases:
            far = b + NEXT_LEG_SUFFIX
            months = _month_index(bars.contract[far]) - _month_index(bars.contract[b])
            ok = bars.tradable[b] & bars.tradable[far] & (months > 0)
            # 年化展期收益 = ln(近月价 / 远月价) × 12 / 相差月数，两腿都用当日真实价格
            raw = np.log(bars.mark_close[b] / bars.mark_close[far]) * 12 / months
            carry[b] = raw.where(ok).rolling(p.smooth, min_periods=1).mean().where(ok)
        k = min(p.top_k, max(1, len(bases) // 2))
        mask = rebalance_mask(bars.dates, p.rebalance)
        long = top_k_weights(carry, k, mask, k * p.position_limit)
        short = top_k_weights(carry, k, mask, k * p.position_limit, ascending=True)
        w = (long - short).fillna(0.0)
        return StrategyOutput(weights=w, rebalance=mask, indicators={"年化展期收益": carry},
                              notes=["只交易主力合约，次主力合约只用来计算期限结构，不持仓。"])


def _month_index(code: pd.Series) -> pd.Series:
    s = code.astype("string").str[-4:]
    yy = pd.to_numeric(s.str[:2], errors="coerce")
    mm = pd.to_numeric(s.str[2:], errors="coerce")
    return (2000 + yy) * 12 + mm
