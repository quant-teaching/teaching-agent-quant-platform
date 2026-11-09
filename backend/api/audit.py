"""回测结果的独立核验：不调用回测引擎，直接读原始行情文件和成交记录，从头重算一遍。

1. 逐笔成交：成交价 = 当日开盘价 ×（1 ± 滑点），手续费 = max(成交额 × 佣金率, 最低佣金) + 卖出印花税；
   期货成交价 = 当日该合约开盘价 ± 滑点跳数 × 最小变动价位。开盘价取自行情快照，学生可以拿行情软件对照；
2. 账本对账（股票）：期初资金 − 买入金额 − 费用 + 卖出金额 + 现金分红 + 期末持仓 × 当日收盘价 = 期末权益；
3. 指标复算在前端用每日净值完成（浏览器独立计算，与后端代码无关）。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from quant.data.catalog import FUTURES_SPECS, NEXT_LEG_SUFFIX
from quant.data.loader import read_dataset
from quant.engine.config import BacktestConfig, stamp_duty_rate
from quant.robustness import _deep_clean

from . import services
from .services import result_path

TRADE_SAMPLE = 200  # 返回给前端逐条展示的成交条数


def _fills(p: dict[str, Any]) -> pd.DataFrame:
    path = result_path(p["id"]).with_name(f"{p['id']}.fills.parquet")
    df = pd.read_parquet(path) if path.exists() else pd.DataFrame(p["fills"])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df


def _stock_market() -> pd.DataFrame:
    s = read_dataset("stock_daily")[["date", "symbol", "open", "close", "close_raw"]].copy()
    s["open_raw"] = (s["open"] * s["close_raw"] / s["close"]).round(2)  # 前复权开盘价还原成当日真实开盘价（按分报价）
    i = read_dataset("industry_daily")[["date", "symbol", "open", "close"]].copy()
    i["open_raw"], i["close_raw"] = i["open"], i["close"]
    m = pd.concat([s, i])[["date", "symbol", "open_raw", "close_raw"]]
    m["date"] = pd.to_datetime(m["date"]).dt.normalize()
    return m.set_index(["date", "symbol"])


def audit(result_id: str) -> dict[str, Any]:
    return _deep_clean(_audit(result_id))  # 转成原生 Python 类型，便于序列化


def _audit(result_id: str) -> dict[str, Any]:
    p = services.load_payload(result_id)
    if p["kind"] != "single":
        return {"supported": False, "reason": "组合回测由各子策略的收益合成，请打开各子策略的报告分别核验。"}
    cfg = BacktestConfig(**p["config"])
    df = _fills(p)
    if df.empty:
        return {"supported": True, "rows": [], "checks": [], "reconcile": None, "note": "这次回测没有成交。"}
    futures = df["symbol"].map(lambda s: s.removesuffix(NEXT_LEG_SUFFIX) in FUTURES_SPECS)
    rows: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    tol = lambda a, b: abs(a - b) <= max(0.01, abs(b) * 1e-6)  # noqa: E731  按分计价，容差 1 分钱

    # ---- 股票与行业指数
    st = df[~futures]
    if not st.empty:
        mkt = _stock_market()
        trades = st[~st["action"].isin(["分红", "送转"])]
        n_ok_p = n_ok_f = 0
        for f in trades.itertuples():
            o = mkt["open_raw"].get((f.date, f.symbol))
            buy = f.qty > 0
            exp_price = None if o is None else o * (1 + cfg.stock_slippage if buy else 1 - cfg.stock_slippage)
            amount = abs(f.qty) * f.price
            comm = max(amount * cfg.stock_commission, cfg.stock_min_commission)
            stamp = 0.0 if buy else amount * stamp_duty_rate(f.date.date())
            price_ok = exp_price is not None and abs(f.price - exp_price) <= max(1e-6, exp_price * 1e-9)
            fee_ok = tol(f.fee, comm + stamp)
            n_ok_p += price_ok
            n_ok_f += fee_ok
            if len(rows) < TRADE_SAMPLE:
                rows.append({
                    "date": f.date.strftime("%Y-%m-%d"), "symbol": f.symbol, "name": f.name, "action": f.action,
                    "qty": f.qty, "open": o, "slippage_rate": cfg.stock_slippage, "expected_price": exp_price,
                    "price": f.price, "price_ok": price_ok, "amount": amount, "commission": comm, "stamp": stamp,
                    "stamp_rate": 0.0 if buy else stamp_duty_rate(f.date.date()), "expected_fee": comm + stamp,
                    "fee": f.fee, "fee_ok": fee_ok,
                })
        checks.append({"name": "成交价 = 当日开盘价 ×（1 ± 滑点）", "ok": n_ok_p == len(trades),
                       "detail": f"{n_ok_p} / {len(trades)} 笔一致"})
        checks.append({"name": "手续费 = max(成交额 × 佣金率, 最低佣金) + 卖出印花税", "ok": n_ok_f == len(trades),
                       "detail": f"{n_ok_f} / {len(trades)} 笔一致"})

    # ---- 期货：成交价核对（盈亏按逐日盯市结算，对账见测试报告中的引擎交叉验证）
    fu = df[futures]
    if not fu.empty:
        raw = read_dataset("futures_continuous")[["date", "symbol", "contract", "open"]].copy()
        raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
        raw = raw.set_index(["date", "symbol"])
        trades = fu[~fu["note"].fillna("").str.contains("→")]  # 换月移仓按前一日收盘价，单独说明
        n_ok = 0
        for f in trades.itertuples():
            spec = FUTURES_SPECS[f.symbol.removesuffix(NEXT_LEG_SUFFIX)]
            try:
                r = raw.loc[(f.date, f.symbol)]
                o = float(r["open"]) if r["contract"] == f.contract else None
            except KeyError:
                o = None
            side = 1 if f.qty > 0 else -1
            exp_price = None if o is None else o + side * spec.tick * cfg.futures_slippage_ticks
            ok = exp_price is not None and abs(f.price - exp_price) < 1e-6
            n_ok += ok
            if len(rows) < TRADE_SAMPLE:
                rows.append({"date": f.date.strftime("%Y-%m-%d"), "symbol": f.symbol, "name": f.name,
                             "action": f.action, "contract": f.contract, "qty": f.qty, "open": o,
                             "tick": spec.tick, "slippage_ticks": cfg.futures_slippage_ticks,
                             "expected_price": exp_price, "price": f.price, "price_ok": ok,
                             "fee": f.fee, "multiplier": spec.multiplier})
        checks.append({"name": "期货成交价 = 当日合约开盘价 ± 滑点跳数 × 最小变动价位", "ok": n_ok == len(trades),
                       "detail": f"{n_ok} / {len(trades)} 笔一致"})

    # ---- 股票账本对账
    reconcile = None
    if fu.empty:
        mkt = _stock_market()
        buys = st[(st["qty"] > 0) & ~st["action"].isin(["分红", "送转"])]
        sells = st[(st["qty"] < 0)]
        divs = st[st["action"] == "分红"]
        held = st[st["action"] != "分红"].groupby("symbol")["qty"].sum()
        held = held[held.abs() > 1e-9]
        last = pd.Timestamp(p["series"]["dates"][-1])
        value, missing = 0.0, []
        holdings = []
        for sym, q in held.items():
            c = mkt["close_raw"].get((last, sym))
            if c is None or pd.isna(c):  # 停牌：用最近一个有行情的收盘价
                hist = mkt["close_raw"].xs(sym, level="symbol").loc[:last].dropna()
                c = float(hist.iloc[-1]) if len(hist) else None
            if c is None:
                missing.append(sym)
                continue
            value += q * c
            holdings.append({"symbol": sym, "qty": float(q), "close": float(c), "value": float(q * c)})
        init = float(cfg.initial_capital)
        buy_amt, sell_amt = float(buys["amount"].sum()), float(sells["amount"].sum())
        fees, div_amt = float(st["fee"].sum()), float(divs["amount"].sum())
        computed = init - buy_amt + sell_amt - fees + div_amt + value
        reported = float(p["metrics"]["final_equity"])
        reconcile = {"date": last.strftime("%Y-%m-%d"), "initial": init, "buy": buy_amt, "sell": sell_amt,
                     "fees": fees, "dividends": div_amt, "holdings_value": value, "holdings": holdings,
                     "computed": computed, "reported": reported, "diff": computed - reported, "missing": missing}
        checks.append({"name": "期初资金 − 买入 + 卖出 − 费用 + 分红 + 期末持仓市值 = 期末权益",
                       "ok": abs(computed - reported) < 1.0, "detail": f"差额 {computed - reported:.2f} 元"})
    return {"supported": True, "rows": rows, "total_fills": int(len(df)), "checks": checks, "reconcile": reconcile,
            "config": {"stock_commission": cfg.stock_commission, "stock_min_commission": cfg.stock_min_commission,
                       "stock_slippage": cfg.stock_slippage, "futures_slippage_ticks": cfg.futures_slippage_ticks,
                       "stamp_before": stamp_duty_rate(date(2023, 8, 27)), "stamp_after": stamp_duty_rate(date(2023, 8, 28))}}
