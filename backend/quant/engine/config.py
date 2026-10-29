"""回测配置与交易成本。默认值取 A 股和国内商品期货的常见水平，均可在回测时修改。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

STAMP_DUTY_CHANGE = date(2023, 8, 28)  # 印花税减半：0.1% → 0.05%


def stamp_duty_rate(on: date) -> float:
    """A 股印花税只在卖出时收取。"""
    return 0.001 if on < STAMP_DUTY_CHANGE else 0.0005


class BacktestConfig(BaseModel):
    start: date = Field(description="回测开始日期")
    end: date = Field(description="回测结束日期")
    initial_capital: float = Field(10_000_000, gt=0, description="初始资金（元）")

    stock_commission: float = Field(0.00025, ge=0, le=0.01, description="股票佣金率（双边）")
    stock_min_commission: float = Field(5.0, ge=0, description="股票单笔最低佣金（元）")
    stock_slippage: float = Field(0.0005, ge=0, le=0.05, description="股票滑点（成交价偏离开盘价的比例）")
    futures_slippage_ticks: float = Field(1, ge=0, le=20, description="期货滑点（最小变动价位的跳数）")
    futures_commission_scale: float = Field(1.0, ge=0, le=10, description="期货手续费相对品种默认费率的倍数")
    max_margin_ratio: float = Field(0.8, gt=0, le=1, description="期货保证金占用上限（占权益比例）")
    min_trade_ratio: float = Field(0.002, ge=0, le=0.1, description="再平衡时忽略小于该权益比例的微调")

    risk_free_rate: float = Field(0.0, ge=0, le=0.2, description="无风险利率（年化），用于夏普比率")
    benchmarks: list[str] = Field(
        default_factory=lambda: ["000300", "000905", "399006"], description="基准指数代码"
    )

    @model_validator(mode="after")
    def _check_dates(self) -> BacktestConfig:
        if self.end <= self.start:
            raise ValueError("结束日期必须晚于开始日期")
        return self
