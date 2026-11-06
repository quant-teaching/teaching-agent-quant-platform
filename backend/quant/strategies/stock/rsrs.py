from pydantic import Field, model_validator

from ..base import Strategy, StrategyOutput, register
from ..common import StopParams, apply_stops, pool_weights, state_machine
from ..indicators import rsrs


class Params(StopParams):
    window: int = Field(18, ge=5, le=60, title="回归窗口",
                        description="用最近 N 日的最高价对最低价做回归得到斜率 β，原研报取 18 日")
    z_window: int = Field(250, ge=60, le=750, title="标准化窗口",
                          description="把 β 与过去 M 日的 β 比较做 Z 分数，判断当前支撑强弱处在历史什么位置")
    buy_z: float = Field(0.7, gt=0, le=3, title="买入阈值", description="标准分高于该值买入（支撑明显强于阻力）")
    sell_z: float = Field(-0.7, ge=-3, lt=0, title="卖出阈值", description="标准分低于该值卖出（阻力明显强于支撑）")
    use_r2: bool = Field(True, title="R² 修正",
                         description="标准分乘以回归的 R²，回归拟合差（高低点关系混乱）时信号自动变弱")
    position_ratio: float = Field(1.0, gt=0, le=1, title="总仓位比例",
                                  description="股票池等分资金后，每只股票满仓时占其资金槽位的比例")

    @model_validator(mode="after")
    def _check(self):
        if self.window >= self.z_window:
            raise ValueError("标准化窗口必须大于回归窗口")
        return self


@register
class RSRSStock(Strategy):
    id = "rsrs_stock"
    name = "RSRS 阻力支撑择时"
    category = "stock"
    style = "择时（量化技术指标）"
    summary = "用最高价对最低价回归的斜率衡量支撑与阻力的相对强弱，斜率的标准分偏高时持有、偏低时空仓。"
    aliases = ("RSRS", "阻力支撑", "阻力支撑相对强度", "RSRS择时", "RSRS 择时")
    Params = Params
    default_universe = "stock_pool"
    asset_types = frozenset({"stock", "industry"})

    def generate(self, bars):
        p = self.params
        beta, r2 = rsrs(bars.high, bars.low, p.window)
        mu = beta.rolling(p.z_window, min_periods=p.z_window // 2).mean()
        sd = beta.rolling(p.z_window, min_periods=p.z_window // 2).std(ddof=0)
        z = (beta - mu) / sd.where(sd > 0)
        if p.use_r2:
            z = z * r2
        pos = state_machine(z > p.buy_z, z < p.sell_z)
        pos = apply_stops(pos, bars.close, p.stop_loss, p.take_profit)
        return StrategyOutput(weights=pool_weights(pos, p.position_ratio),
                              indicators={"RSRS 斜率": beta, "RSRS 标准分": z})
