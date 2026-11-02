"""回测引擎：逐日撮合。

时间线（每个交易日 t）：
0. 分红送转：t 日是除权日时，t-1 日收盘的股票持仓按每股派息收到现金，按送转比例增加股数；
1. 期货换月：t-1 日收盘时把旧合约持仓移到新合约，计移仓手续费和滑点；
2. 开盘撮合：读取策略在 t-1 日收盘后给出的目标权重，按 t 日开盘价加减滑点成交，先卖后买；
3. 收盘盯市：股票按收盘价计市值，期货按"手数 × 乘数 × 价差"把当日盈亏结算进现金。

因为信号在 t-1 日收盘生成、t 日开盘才成交，策略不可能用到成交当天的信息（没有未来函数），
A 股"当天买入、次日才能卖出"的 T+1 规则也自然满足。

目标权重的含义：持仓名义市值 / 前一日收盘权益。股票只能为非负；期货为负表示做空，
所有期货权重绝对值之和就是名义杠杆，保证金占用超过上限时等比例缩减。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..data.catalog import STOCKS, futures_spec
from ..data.loader import Bars, DataError, symbol_name
from .config import BacktestConfig, stamp_duty_rate
from .ledger import Ledger, Trade

EPS = 1e-9
CORP_ACTIONS = ("分红", "送转")  # 公司行为产生的记录，不是交易，不计入成交笔数、换手和买卖点
NON_TRADES = ("移仓", *CORP_ACTIONS)


@dataclass
class Fill:
    date: pd.Timestamp
    symbol: str
    name: str
    action: str
    qty: float
    price: float
    amount: float
    fee: float
    slippage: float
    contract: str | None = None
    note: str = ""


@dataclass
class EngineOutput:
    daily: pd.DataFrame  # equity, cash, market_value, gross_exposure, net_exposure, margin, turnover
    positions: pd.DataFrame  # 长表：date, symbol, qty, price, value, weight, contract
    fills: list[Fill]
    trades: list[Trade]
    warnings: list[str] = field(default_factory=list)
    blocked: int = 0  # 因涨跌停、停牌、资金不足未能成交的次数
    dividends: float = 0.0  # 累计收到的现金分红（元）


def _lot(symbol: str, kind: str) -> float:
    return 100.0 if kind == "stock" else 1.0


def _action(kind: str, q_old: float, q_new: float) -> str:
    if kind != "futures":
        return "买入" if q_new > q_old else "卖出"
    if q_old >= 0 and q_new > q_old:
        return "开多" if q_old == 0 else "加多"
    if q_old <= 0 and q_new < q_old:
        return "开空" if q_old == 0 else "加空"
    if q_old > 0 and q_new < 0:
        return "平多反手开空"
    if q_old < 0 and q_new > 0:
        return "平空反手开多"
    return "平多" if q_old > 0 else "平空"


def run_engine(
    weights: pd.DataFrame,
    bars: Bars,
    cfg: BacktestConfig,
    rebalance: pd.Series | None = None,
) -> EngineOutput:
    symbols = list(weights.columns)
    kinds = [bars.types[s] for s in symbols]
    is_fut = np.array([k == "futures" for k in kinds])
    mult = np.array([futures_spec(s).multiplier if f else 1.0 for s, f in zip(symbols, is_fut)])
    tick = np.array([futures_spec(s).tick if f else 0.0 for s, f in zip(symbols, is_fut)])
    margin_rate = np.array([futures_spec(s).margin_rate if f else 0.0 for s, f in zip(symbols, is_fut)])
    fut_comm = np.array(
        [futures_spec(s).commission_rate * cfg.futures_commission_scale if f else 0.0
         for s, f in zip(symbols, is_fut)]
    )
    lots = np.array([_lot(s, k) for s, k in zip(symbols, kinds)])
    names = [symbol_name(s) for s in symbols]

    full_index = bars.dates
    start, end = pd.Timestamp(cfg.start), pd.Timestamp(cfg.end)
    in_range = (full_index >= start) & (full_index <= end)
    days = full_index[in_range]
    if len(days) < 2:
        raise DataError(f"{cfg.start} 至 {cfg.end} 区间内交易日不足，请检查回测区间是否在数据范围内")

    # 策略在 t-1 日收盘给出的目标，在 t 日执行
    w = weights.reindex(index=full_index).ffill().fillna(0.0)
    desired = w.shift(1).fillna(0.0).loc[days].to_numpy(copy=True)
    if rebalance is not None:
        rb = rebalance.reindex(full_index).fillna(False).astype(bool).shift(1, fill_value=False)
        force = rb.loc[days].to_numpy()
    else:
        force = np.zeros(len(days), dtype=bool)

    warnings: list[str] = []
    if (desired[:, ~is_fut] < -EPS).any():
        warnings.append("A 股不能直接做空，股票的负权重已按 0 处理")
        desired[:, ~is_fut] = np.clip(desired[:, ~is_fut], 0, None)

    sl = slice(int(np.argmax(in_range)), int(np.argmax(in_range)) + len(days))
    prev_i = int(np.argmax(in_range)) - 1
    exec_open = bars.exec_open[symbols].to_numpy()[sl]
    mclose = bars.mark_close[symbols].to_numpy()[sl]
    mpre = bars.mark_pre_close[symbols].to_numpy()[sl]
    tradable = bars.tradable[symbols].to_numpy()[sl]
    roll = bars.roll[symbols].to_numpy()[sl]
    contract = bars.contract[symbols].to_numpy()[sl]
    zeros = pd.DataFrame(0.0, index=full_index, columns=symbols)
    cash_div = bars.extra.get("cash_div", zeros).reindex(columns=symbols).fillna(0.0).to_numpy()[sl]
    split = bars.extra.get("split", zeros + 1.0).reindex(columns=symbols).fillna(1.0).to_numpy()[sl]
    has_ca = (~is_fut)[None, :] & ((cash_div > 0) | (split != 1.0))
    prev_mclose_all = bars.mark_close[symbols].to_numpy()
    first_prev_close = prev_mclose_all[prev_i] if prev_i >= 0 else np.full(len(symbols), np.nan)

    n = len(symbols)
    qty = np.zeros(n)
    mark = np.full(n, np.nan)  # 期货盯市基准价
    applied = np.full(n, np.nan)  # 已执行到的目标权重
    cash = cfg.initial_capital
    equity = cfg.initial_capital
    ledgers = [Ledger(s, multiplier=m) for s, m in zip(symbols, mult)]
    fills: list[Fill] = []
    pos_days: list[int] = []  # 每天收盘的持仓快照：第几个交易日、持有哪些标的、数量
    pos_idx: list[np.ndarray] = []
    pos_qty: list[np.ndarray] = []
    daily_rows: list[dict] = []
    blocked = 0
    dividends = 0.0
    late_listing = set()

    for di, t in enumerate(days):
        tdate = t.date()
        prev_equity = equity
        traded_value = 0.0

        # 0. 分红送转（第一天的持仓为空，不会触发）
        for j in np.nonzero(has_ca[di] & (qty > 0))[0]:
            if cash_div[di, j] > 0:
                amount = qty[j] * cash_div[di, j]
                cash += amount
                dividends += amount
                ledgers[j].dividend(amount)
                fills.append(Fill(t, symbols[j], names[j], "分红", qty[j], cash_div[di, j], amount, 0.0, 0.0,
                                  note=f"每股派息 {cash_div[di, j]:.4g} 元"))
            if split[di, j] != 1.0:
                added = round(qty[j] * (split[di, j] - 1))
                qty[j] += added
                ledgers[j].split(split[di, j])
                fills.append(Fill(t, symbols[j], names[j], "送转", added, 0.0, 0.0, 0.0, 0.0,
                                  note=f"每 10 股送转 {round((split[di, j] - 1) * 10, 1):g} 股"))

        # 1. 期货换月
        for j in np.nonzero(is_fut & roll[di] & (qty != 0))[0]:
            old_p = mclose[di - 1, j] if di > 0 else first_prev_close[j]
            new_p = mpre[di, j]
            q = abs(qty[j])
            fee = q * mult[j] * (old_p + new_p) * fut_comm[j]
            slip = q * mult[j] * tick[j] * cfg.futures_slippage_ticks * 2
            cash -= fee + slip
            ledgers[j].roll(old_p, new_p, fee + slip)
            mark[j] = new_p
            old_c = contract[di - 1, j] if di > 0 else ""
            fills.append(Fill(t, symbols[j], names[j], "移仓", qty[j], new_p, q * mult[j] * new_p,
                              fee, slip, contract[di, j], f"{old_c} → {contract[di, j]}"))

        # 2. 开盘撮合。先用数组筛出今天需要处理的标的（目标变了、首次建仓或强制再平衡），
        #    大多数交易日目标不变，逐个标的的循环只在少数标的上进行
        tr = tradable[di]
        never = np.isnan(applied)
        for j in np.nonzero(~tr & (desired[di] > EPS) & never & (qty == 0))[0]:
            late_listing.add(symbols[j])
        with np.errstate(invalid="ignore"):
            todo = tr & (exec_open[di] > 0) & (force[di] | never | (np.abs(desired[di] - applied) >= EPS))
        orders = []
        for j in np.nonzero(todo)[0]:
            target_w = desired[di, j]
            price = exec_open[di, j]
            if is_fut[j]:
                target_q = math.trunc(target_w * prev_equity / (price * mult[j]))
            else:
                target_q = math.floor(target_w * prev_equity / (price * lots[j]) + EPS) * lots[j]
            dq = target_q - qty[j]
            if force[di] and abs(dq) * price * mult[j] < cfg.min_trade_ratio * prev_equity \
                    and target_q != 0:
                applied[j] = target_w
                continue
            if dq == 0:
                applied[j] = target_w
                continue
            orders.append((j, dq, target_w))
        # 先执行减少敞口的订单，释放现金和保证金
        orders.sort(key=lambda o: abs(qty[o[0]] + o[1]) - abs(qty[o[0]]))

        for j, dq, target_w in orders:
            price = exec_open[di, j]
            sym = symbols[j]
            if is_fut[j]:
                if abs(qty[j] + dq) > abs(qty[j]):  # 增加敞口时检查保证金
                    used = float(np.nansum(np.abs(qty) * np.where(is_fut, exec_open[di], 0) * mult
                                           * margin_rate))
                    room = cfg.max_margin_ratio * prev_equity - used
                    per_lot = price * mult[j] * margin_rate[j]
                    add_lots = abs(qty[j] + dq) - abs(qty[j])
                    if add_lots * per_lot > room:
                        allowed = max(0, math.floor(room / per_lot))
                        if allowed == 0:
                            blocked += 1
                            applied[j] = target_w
                            continue
                        dq = math.copysign(abs(dq) - (add_lots - allowed), dq)
                fill = price + math.copysign(tick[j] * cfg.futures_slippage_ticks, dq)
                if not np.isnan(mark[j]) and qty[j] != 0:
                    cash += qty[j] * mult[j] * (price - mark[j])
                slip = abs(dq) * mult[j] * abs(fill - price)
                fee = abs(dq) * mult[j] * fill * fut_comm[j]
                cash -= slip + fee
                mark[j] = price
                q_old = qty[j]
                qty[j] += dq
                ledgers[j].fill(t, dq, fill, fee)  # 成交价已含滑点，成本只计手续费
                fills.append(Fill(t, sym, names[j], _action("futures", q_old, qty[j]), dq, fill,
                                  abs(dq) * mult[j] * fill, fee, slip, contract[di, j]))
                traded_value += abs(dq) * mult[j] * fill
                applied[j] = target_w
                continue

            # 股票 / 行业指数
            if bars.types[sym] == "stock":
                limit = STOCKS[sym].limit_pct(tdate)
                pre = mpre[di, j]
                if pre > 0:
                    if dq > 0 and price >= pre * (1 + limit) - 0.011:
                        blocked += 1
                        continue  # 开盘涨停买不进，明天再试
                    if dq < 0 and price <= pre * (1 - limit) + 0.011:
                        blocked += 1
                        continue  # 开盘跌停卖不出
            slip_rate = cfg.stock_slippage
            if dq > 0:
                fill = price * (1 + slip_rate)
                per_share = fill * (1 + cfg.stock_commission)
                affordable = math.floor(cash / per_share / lots[j] + EPS) * lots[j]
                if affordable < dq:
                    dq = affordable
                    if dq <= 0:
                        blocked += 1
                        applied[j] = target_w
                        continue
                amount = dq * fill
                fee = max(amount * cfg.stock_commission, cfg.stock_min_commission)
                if amount + fee > cash:
                    dq -= lots[j]
                    if dq <= 0:
                        blocked += 1
                        applied[j] = target_w
                        continue
                    amount = dq * fill
                    fee = max(amount * cfg.stock_commission, cfg.stock_min_commission)
                cash -= amount + fee
            else:
                fill = price * (1 - slip_rate)
                amount = -dq * fill
                fee = max(amount * cfg.stock_commission, cfg.stock_min_commission) \
                    + amount * stamp_duty_rate(tdate)
                cash += amount - fee
            slip = abs(dq) * abs(fill - price)
            q_old = qty[j]
            qty[j] += dq
            ledgers[j].fill(t, dq, fill, fee)  # 成交价已含滑点，成本只计手续费
            fills.append(Fill(t, sym, names[j], _action("stock", q_old, qty[j]), dq, fill,
                              abs(dq) * fill, fee, slip))
            traded_value += abs(dq) * fill
            applied[j] = target_w

        # 3. 收盘盯市（向量化）：期货把当日价差盈亏结算进现金，股票按收盘价计市值
        held = qty != 0
        px = mclose[di]
        settle = held & is_fut & tr
        if settle.any():
            base = np.where(np.isnan(mark), mpre[di], mark)
            cash += float(np.sum((qty * mult * (px - base))[settle]))
            mark[settle] = px[settle]
        value = np.where(held, qty * mult * px, 0.0)  # 股票 mult 为 1：市值；期货：名义价值
        stock_value = float(value[held & ~is_fut].sum())
        gross = float(np.abs(value).sum())
        net = float(value.sum())
        margin = float((np.abs(value) * margin_rate).sum())
        held_idx = np.nonzero(held)[0]
        for j in held_idx:
            ledgers[j].bar()
        pos_days.append(di)
        pos_qty.append(qty[held_idx].copy())
        pos_idx.append(held_idx)
        equity = cash + stock_value
        if equity <= 0:
            warnings.append(f"{tdate} 权益归零，回测提前终止（杠杆过高或连续亏损）")
            daily_rows.append(_daily(t, equity, cash, stock_value, gross, net, margin, traded_value,
                                     prev_equity))
            break
        daily_rows.append(_daily(t, equity, cash, stock_value, gross, net, margin, traded_value,
                                 prev_equity))

    daily = pd.DataFrame(daily_rows).set_index("date")
    positions = _positions(days, pos_days, pos_idx, pos_qty, symbols, mclose, mult, contract)
    if not positions.empty:
        positions["weight"] = positions["value"] / positions["date"].map(daily["equity"])
    trades = [t for lg in ledgers for t in lg.trades]
    last = daily.index[-1]
    last_i = len(daily) - 1
    for j, lg in enumerate(ledgers):
        ot = lg.open_trade(last, mclose[last_i, j])
        if ot is not None:
            trades.append(ot)
    trades.sort(key=lambda x: (x.entry_date, x.symbol))
    if late_listing:
        warnings.append(
            "以下标的在回测开始时尚未上市或停牌，有数据后才开始交易：" + "、".join(sorted(late_listing))
        )
    return EngineOutput(daily, positions, fills, trades, warnings, blocked, dividends)


def _positions(days, pos_days, pos_idx, pos_qty, symbols, mclose, mult, contract) -> pd.DataFrame:
    """把每日持仓快照拼成长表：date, symbol, qty, price, value, contract。"""
    cols = ["date", "symbol", "qty", "price", "value", "contract"]
    counts = [len(i) for i in pos_idx]
    if not sum(counts):
        return pd.DataFrame(columns=cols)
    d = np.repeat(np.asarray(pos_days), counts)
    j = np.concatenate(pos_idx)
    q = np.concatenate(pos_qty)
    price = mclose[d, j]
    return pd.DataFrame({
        "date": days[d], "symbol": np.asarray(symbols, dtype=object)[j], "qty": q, "price": price,
        "value": q * mult[j] * price, "contract": contract[d, j],
    })


def _daily(t, equity, cash, stock_value, gross, net, margin, traded, prev_equity) -> dict:
    return {
        "date": t,
        "equity": equity,
        "cash": cash,
        "market_value": stock_value,
        "gross_exposure": gross / equity if equity > 0 else 0.0,
        "net_exposure": net / equity if equity > 0 else 0.0,
        "margin": margin,
        "turnover": traded / prev_equity if prev_equity > 0 else 0.0,
    }
