import numpy as np
from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, StrategyParams, register
from ..common import state_machine


class Params(StrategyParams):
    pairs: str = Field("RB-HC,Y-P", title="品种对",
                       description="用逗号分隔的多个'品种A-品种B'，应选择产业链相关、价格长期联动的品种，如螺纹钢-热卷、豆油-棕榈油")
    window: int = Field(60, ge=10, le=250, title="比价均值窗口", description="估计两品种比价正常水平的天数")
    entry_z: float = Field(2.0, gt=0, le=5, title="开仓 Z 值", description="对数比价偏离均值超过几个标准差时开仓")
    exit_z: float = Field(0.5, ge=0, le=3, title="平仓 Z 值", description="比价回到均值附近几个标准差以内时平仓")
    stop_z: float = Field(4.0, gt=0, le=10, title="止损 Z 值", description="偏离继续扩大到几个标准差时认输止损（联动关系可能已被打破）")
    leg_weight: float = Field(0.15, gt=0, le=1, title="单腿仓位", description="每条腿名义市值占权益的比例，两腿方向相反、金额相等")

    @model_validator(mode="after")
    def _check(self):
        if not self.exit_z < self.entry_z < self.stop_z:
            raise ValueError("需要满足：平仓 Z 值 < 开仓 Z 值 < 止损 Z 值")
        return self


def parse_pairs(text: str) -> list[tuple[str, str]]:
    out = []
    for item in text.replace("，", ",").split(","):
        if not item.strip():
            continue
        parts = [x.strip().upper() for x in item.replace("/", "-").split("-")]
        if len(parts) != 2 or not all(parts) or parts[0] == parts[1]:
            raise ValueError(f"品种对格式应为'品种A-品种B'，例如 RB-HC，收到：{item.strip()}")
        out.append((parts[0], parts[1]))
    if not out:
        raise ValueError("至少需要一个品种对，例如 RB-HC")
    return out


@register
class PairSpreadFutures(Strategy):
    id = "pair_spread_futures"
    name = "跨品种价差套利"
    category = "futures"
    style = "统计套利（配对交易）"
    summary = "选两个产业链相关的品种（如螺纹钢和热卷），两者对数比价偏离历史均值时做空偏贵的、做多偏便宜的，等比价回归后平仓。"
    aliases = ("跨品种套利", "配对交易", "品种对冲", "跨品种价差", "pairs trading", "比价套利")
    Params = Params
    default_universe = "RB,HC,Y,P"
    asset_types = frozenset({"futures"})
    min_symbols = 2

    def generate(self, bars):
        p = self.params
        pairs = parse_pairs(p.pairs)
        w = bars.close * 0.0
        z_all = bars.close * np.nan
        notes, used = [], set()
        for a, b in pairs:
            if a not in bars.symbols or b not in bars.symbols:
                notes.append(f"品种对 {a}-{b} 不在本次标的池中，已跳过（标的池需要同时包含两个品种）。")
                continue
            if a in used or b in used:
                notes.append(f"品种对 {a}-{b} 与其他品种对共用了品种，已跳过以免仓位叠加。")
                continue
            used |= {a, b}
            # 用比例后复权连续价格计算比价，换月不会造成比价跳变
            ratio = np.log(bars.close[a] / bars.close[b]).where(bars.tradable[a] & bars.tradable[b])
            m = ratio.rolling(p.window, min_periods=p.window).mean()
            s = ratio.rolling(p.window, min_periods=p.window).std(ddof=0)
            z = ((ratio - m) / s.replace(0, np.nan)).to_frame("z")
            # 比价偏低（A 相对便宜）→ 多 A 空 B，记为 +1；偏高 → 空 A 多 B，记为 −1
            pos = state_machine((z < -p.entry_z) & (z > -p.stop_z), (z > -p.exit_z) | (z < -p.stop_z) | z.isna(),
                                (z > p.entry_z) & (z < p.stop_z), (z < p.exit_z) | (z > p.stop_z) | z.isna())["z"]
            w[a] = pos * p.leg_weight
            w[b] = -pos * p.leg_weight
            z_all[a] = z["z"]
        if not used:
            raise ValueError("没有可交易的品种对：请确认标的池包含品种对中的两个品种，例如标的池 RB,HC 配合品种对 RB-HC")
        return StrategyOutput(weights=w, indicators={"比价Z值": z_all}, notes=notes)
