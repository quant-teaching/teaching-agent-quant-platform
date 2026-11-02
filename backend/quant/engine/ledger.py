"""单个标的的持仓账本：平均成本法记录持仓，按"从空仓到再次空仓"切分出一笔完整交易。

一笔交易（round trip）的盈亏 = 已实现价差盈亏 − 期间全部手续费与滑点，用于计算胜率和盈亏比。
期货换月不结束交易，只把旧合约的浮盈亏转为已实现，再以新合约价格作为持仓成本继续持有。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Trade:
    symbol: str
    side: str  # "多" / "空"
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp | None
    entry_price: float  # 加仓后的平均开仓价
    exit_price: float | None  # 平均平仓价
    max_qty: float
    pnl: float  # 净盈亏（已扣成本）
    cost: float  # 手续费（成交价已含滑点；期货换月的移仓滑点计入此项）
    holding_days: int
    is_open: bool = False
    return_pct: float = 0.0  # 净盈亏 / 最大持仓占用的开仓金额


@dataclass
class _Episode:
    side: int
    entry_date: pd.Timestamp
    entry_value: float = 0.0
    entry_qty: float = 0.0
    exit_value: float = 0.0
    exit_qty: float = 0.0
    realized: float = 0.0
    cost: float = 0.0
    max_qty: float = 0.0
    max_value: float = 0.0
    bars: int = 0


@dataclass
class Ledger:
    symbol: str
    multiplier: float = 1.0
    qty: float = 0.0
    avg: float = 0.0
    trades: list[Trade] = field(default_factory=list)
    _ep: _Episode | None = None

    def fill(self, when: pd.Timestamp, dq: float, price: float, cost: float) -> None:
        """记录一次成交。dq 为带符号的数量变化，cost 为本次手续费加滑点。"""
        if dq == 0:
            return
        if self.qty == 0:
            self._open(when, dq, price, cost)
            return
        same_dir = (self.qty > 0) == (dq > 0)
        if same_dir:
            new_qty = self.qty + dq
            self.avg = (self.avg * abs(self.qty) + price * abs(dq)) / abs(new_qty)
            self.qty = new_qty
            ep = self._ep
            ep.entry_value += abs(dq) * price
            ep.entry_qty += abs(dq)
            ep.cost += cost
            ep.max_qty = max(ep.max_qty, abs(self.qty))
            ep.max_value = max(ep.max_value, abs(self.qty) * self.avg * self.multiplier)
            return
        closed = min(abs(dq), abs(self.qty))
        ratio = closed / abs(dq)
        ep = self._ep
        ep.realized += closed * (price - self.avg) * self.multiplier * (1 if self.qty > 0 else -1)
        ep.exit_value += closed * price
        ep.exit_qty += closed
        ep.cost += cost * ratio
        self.qty += closed * (1 if dq > 0 else -1)
        if self.qty == 0:
            self._close(when)
        remaining = abs(dq) - closed
        if remaining > 0:  # 反手
            self._open(when, remaining * (1 if dq > 0 else -1), price, cost * (1 - ratio))

    def roll(self, old_price: float, new_price: float, cost: float) -> None:
        """期货换月：旧合约按 old_price 平仓、新合约按 new_price 开仓。"""
        if self.qty == 0:
            return
        ep = self._ep
        ep.realized += self.qty * (old_price - self.avg) * self.multiplier
        ep.cost += cost
        # 换月后成本价按新合约重置，开仓均价按比例换算，保持"均价"的可比性
        scale = new_price / old_price if old_price else 1.0
        ep.entry_value *= scale
        ep.exit_value *= scale
        self.avg = new_price

    def dividend(self, amount: float) -> None:
        """现金分红计入这笔交易的已实现盈亏。"""
        if self._ep is not None:
            self._ep.realized += amount

    def split(self, ratio: float) -> None:
        """送转股：股数乘以 ratio，成本价除以 ratio，总成本不变；均价都换算成送转后的口径。"""
        if self.qty == 0 or ratio == 1:
            return
        self.qty = round(self.qty * ratio)
        self.avg /= ratio
        ep = self._ep
        ep.entry_qty *= ratio
        ep.exit_qty *= ratio
        ep.max_qty = max(ep.max_qty * ratio, abs(self.qty))

    def bar(self) -> None:
        if self._ep is not None:
            self._ep.bars += 1

    def open_trade(self, when: pd.Timestamp, mark: float) -> Trade | None:
        """回测结束时仍未平仓的交易，按收盘价计算浮动盈亏。"""
        if self._ep is None or self.qty == 0:
            return None
        ep = self._ep
        unreal = self.qty * (mark - self.avg) * self.multiplier
        t = self._make(ep, when, None)
        t.pnl = ep.realized + unreal - ep.cost
        t.is_open = True
        t.return_pct = t.pnl / ep.max_value if ep.max_value else 0.0
        return t

    def _open(self, when: pd.Timestamp, dq: float, price: float, cost: float) -> None:
        self.qty = dq
        self.avg = price
        self._ep = _Episode(
            side=1 if dq > 0 else -1, entry_date=when, entry_value=abs(dq) * price,
            entry_qty=abs(dq), cost=cost, max_qty=abs(dq),
            max_value=abs(dq) * price * self.multiplier,
        )

    def _close(self, when: pd.Timestamp) -> None:
        ep = self._ep
        t = self._make(ep, when, ep.exit_value / ep.exit_qty if ep.exit_qty else None)
        t.pnl = ep.realized - ep.cost
        t.return_pct = t.pnl / ep.max_value if ep.max_value else 0.0
        self.trades.append(t)
        self._ep = None
        self.avg = 0.0

    def _make(self, ep: _Episode, when: pd.Timestamp, exit_price: float | None) -> Trade:
        return Trade(
            symbol=self.symbol,
            side="多" if ep.side > 0 else "空",
            entry_date=ep.entry_date,
            exit_date=when,
            entry_price=ep.entry_value / ep.entry_qty if ep.entry_qty else 0.0,
            exit_price=exit_price,
            max_qty=ep.max_qty,
            pnl=0.0,
            cost=ep.cost,
            holding_days=ep.bars,
        )
