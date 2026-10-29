import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..indicators import atr, donchian


class Params(StrategyParams):
    entry_window: int = Field(20, ge=5, le=120, title="入场通道周期",
                              description="收盘价突破过去 N 日最高价做多、跌破最低价做空（原版系统一为 20 日）")
    exit_window: int = Field(10, ge=3, le=60, title="离场通道周期",
                             description="多头跌破过去 M 日最低价离场、空头升破最高价离场，应小于入场周期")
    atr_period: int = Field(20, ge=5, le=60, title="ATR 周期",
                            description="计算波动单位 N 的天数，越大 N 越平滑、加仓与止损距离越稳定")
    risk_per_unit: float = Field(0.01, gt=0, le=0.05, title="单位风险比例",
                                 description="每个头寸单位在价格波动 1N 时亏损占权益的比例，原版为 1%")
    max_units: int = Field(4, ge=1, le=8, title="最大加仓单位数", description="单个品种最多持有的头寸单位数")
    add_step: float = Field(0.5, gt=0, le=3, title="加仓间距（N）",
                            description="价格每朝有利方向移动多少个 N 加仓一个单位")
    stop_atr: float = Field(2.0, gt=0, le=6, title="止损距离（N）",
                            description="价格从最后一次加仓价反向移动多少个 N 止损，原版为 2N")
    position_limit: float = Field(0.2, gt=0, le=1, title="单品种仓位上限",
                                  description="单个品种所有单位合计的名义市值占权益比例上限")
    allow_short: bool = Field(True, title="允许做空", description="关闭后只做多头突破")

    @model_validator(mode="after")
    def _check(self):
        if self.exit_window >= self.entry_window:
            raise ValueError("离场通道周期应小于入场通道周期")
        return self


@register
class TurtleFutures(Strategy):
    id = "turtle_futures"
    name = "海龟交易法则"
    category = "futures"
    style = "趋势跟踪（通道突破）"
    summary = "价格突破 N 日高点做多、跌破低点做空，按 ATR 计算头寸并金字塔加仓，2N 止损，完整的机械化趋势交易系统。"
    aliases = ("海龟", "海龟交易", "海龟策略", "海龟交易期货", "turtle")
    Params = Params
    default_universe = "futures"
    asset_types = frozenset({"futures"})

    def generate(self, bars):
        p = self.params
        c, h, lo = bars.close, bars.high, bars.low
        n = atr(h, lo, c, p.atr_period)
        up_in, lo_in = donchian(h, lo, p.entry_window)
        up_out, lo_out = donchian(h, lo, p.exit_window)
        unit_cap = p.position_limit / p.max_units

        C, N = c.to_numpy(float), n.to_numpy(float)
        UI, LI, UO, LO = (x.to_numpy(float) for x in (up_in, lo_in, up_out, lo_out))
        T, K = C.shape
        w = np.zeros((T, K))
        side = np.zeros(K)  # 1 多 / −1 空 / 0 空仓
        units = np.zeros(K)
        last_px = np.full(K, np.nan)  # 最后一次加仓的价格
        unit_w = np.zeros(K)  # 每单位的权重（开仓时按当时的 N 固定）
        stop = np.full(K, np.nan)
        for t in range(T):
            px, nn = C[t], N[t]
            valid = ~np.isnan(px) & ~np.isnan(nn) & (nn > 0)
            # 1. 持仓的离场与止损
            exit_long = (side > 0) & ((px < LO[t]) | (px < stop))
            exit_short = (side < 0) & ((px > UO[t]) | (px > stop))
            out = valid & (exit_long | exit_short)
            side[out], units[out] = 0, 0
            # 2. 加仓：每朝有利方向走 add_step 个 N 加一个单位，止损跟随上移
            for sgn in (1, -1):
                can_add = valid & (side == sgn) & (units < p.max_units) & \
                    (sgn * (px - last_px) >= p.add_step * nn)
                units[can_add] += 1
                last_px[can_add] = px[can_add]
                stop[can_add] = px[can_add] - sgn * p.stop_atr * nn[can_add]
            # 3. 新开仓：收盘突破入场通道
            flat = valid & (side == 0)
            go_long = flat & (px > UI[t])
            go_short = flat & (px < LI[t]) & p.allow_short
            for mask, sgn in ((go_long, 1), (go_short, -1)):
                side[mask], units[mask] = sgn, 1
                last_px[mask] = px[mask]
                stop[mask] = px[mask] - sgn * p.stop_atr * nn[mask]
                # 头寸单位：1N 的价格波动造成 risk_per_unit 的权益亏损 → 名义权重 = 风险比例 × 价格 / N
                unit_w[mask] = np.minimum(p.risk_per_unit * px[mask] / nn[mask], unit_cap)
            w[t] = side * units * unit_w
        weights = pd.DataFrame(w, index=c.index, columns=c.columns)
        return StrategyOutput(
            weights=weights,
            indicators={f"{p.entry_window}日高点": up_in, f"{p.entry_window}日低点": lo_in,
                        f"{p.exit_window}日离场高点": up_out, f"{p.exit_window}日离场低点": lo_out,
                        "ATR(N)": n},
        )
