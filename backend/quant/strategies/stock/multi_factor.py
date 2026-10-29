from typing import Literal

import pandas as pd
from pydantic import Field, model_validator

from ...data.loader import load_dividends
from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import rebalance_mask, top_k_weights
from ..indicators import cs_zscore, momentum, realized_vol


class Params(StrategyParams):
    w_momentum: float = Field(1.0, ge=-3, le=3, title="动量因子权重",
                              description="过去 120 日（跳过最近 20 日）涨幅，权重为正表示偏好强势股")
    w_low_vol: float = Field(1.0, ge=-3, le=3, title="低波动因子权重",
                             description="60 日波动率取负，权重为正表示偏好波动小的股票（低波动异象）")
    w_reversal: float = Field(0.5, ge=-3, le=3, title="短期反转因子权重",
                              description="最近 20 日涨幅取负，权重为正表示偏好近期回调的股票")
    w_liquidity: float = Field(0.5, ge=-3, le=3, title="低换手因子权重",
                               description="20 日平均换手率取负，权重为正表示偏好交易不拥挤的股票")
    w_dividend: float = Field(1.0, ge=-3, le=3, title="股息率因子权重",
                              description="过去一年每股分红 / 股价，权重为正表示偏好高股息（价值风格）")
    top_k: int = Field(10, ge=1, le=30, title="持股数量", description="综合得分最高的前 K 只股票等权持有")
    rebalance: Literal["M", "Q"] = Field("M", title="调仓频率", description="M 每月、Q 每季度")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例", description="满仓时股票占总资金的比例")

    @model_validator(mode="after")
    def _check(self):
        if not any([self.w_momentum, self.w_low_vol, self.w_reversal, self.w_liquidity, self.w_dividend]):
            raise ValueError("至少需要一个非零的因子权重")
        return self


def trailing_dividend_yield(bars) -> pd.DataFrame:
    """过去 365 天内已除息的每股现金分红合计 / 当日不复权收盘价。以除息日为信息可得日，没有未来函数。"""
    raw = bars.extra.get("close_raw")
    if raw is None:
        return pd.DataFrame(index=bars.dates, columns=bars.symbols, dtype=float)
    div = load_dividends()
    div = div[div["symbol"].isin(bars.symbols)]
    daily = div.pivot_table(index="ex_date", columns="symbol", values="cash_per_share", aggfunc="sum")
    daily = daily.reindex(columns=bars.symbols)
    idx = bars.dates.union(daily.index)
    daily = daily.reindex(idx).fillna(0.0)
    ttm = daily.rolling("365D").sum().reindex(bars.dates)
    return (ttm / raw).where(raw.notna())


@register
class MultiFactorStock(Strategy):
    id = "multi_factor_stock"
    name = "多因子选股"
    category = "stock"
    style = "多因子"
    summary = "把动量、低波动、反转、换手、股息率五个因子标准化后加权打分，定期买入得分最高的股票。"
    aliases = ("多因子", "因子选股", "打分选股", "多因子模型")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock"})
    min_symbols = 5

    def generate(self, bars):
        p = self.params
        c = bars.close
        turnover = bars.extra.get("turnover")
        factors = {
            "动量": (p.w_momentum, momentum(c, 120, 20)),
            "低波动": (p.w_low_vol, -realized_vol(c, 60)),
            "短期反转": (p.w_reversal, -momentum(c, 20)),
            "低换手": (p.w_liquidity, -turnover.rolling(20, min_periods=10).mean()
                     if turnover is not None else None),
            "股息率": (p.w_dividend, trailing_dividend_yield(bars) if p.w_dividend else None),
        }
        score = None
        used = {}
        for name, (w, f) in factors.items():
            if not w or f is None:
                continue
            z = cs_zscore(f.where(bars.tradable)).clip(-3, 3)
            used[name] = z
            score = z * w if score is None else score.add(z * w, fill_value=0)
        # 关键因子缺失（如上市不满 120 日）的股票不参与打分
        score = score.where(momentum(c, 120, 20).notna() & bars.tradable)
        mask = rebalance_mask(bars.dates, p.rebalance)
        w = top_k_weights(score, min(p.top_k, len(bars.symbols)), mask, p.position_ratio)
        return StrategyOutput(weights=w, rebalance=mask, indicators={"综合得分": score, **used})
