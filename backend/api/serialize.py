"""回测结果 → 前端 JSON。时间序列转成列式数组，NaN 转成 null。"""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from quant.backtest import BacktestResult, trade_to_dict
from quant.data.loader import symbol_name

MAX_FILLS = 5000


def clean(x: Any) -> Any:
    """递归把 NaN/inf 转 None、numpy 标量转 Python、时间转字符串。"""
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [clean(v) for v in x]
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float):
        return None if math.isnan(x) or math.isinf(x) else round(x, 6)
    if isinstance(x, pd.Timestamp):
        return str(x.date())
    return x


def _arr(s: pd.Series, nd: int = 6) -> list:
    return [None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), nd)
            for v in s.tolist()]


def result_payload(r: BacktestResult) -> dict[str, Any]:
    s = r.series
    dates = [str(d.date()) for d in s.index]
    benches = {}
    for code, b in r.benchmarks.items():
        benches[code] = {"name": b["name"], "nav": _arr(s[f"bench_{code}"]), "drawdown": _arr(s[f"bench_dd_{code}"])}
    comps = {c.removeprefix("comp_"): _arr(s[c]) for c in s.columns if c.startswith("comp_")}

    yearly = r.yearly
    monthly = [{"month": str(d.to_period("M")), "ret": None if math.isnan(v) else round(float(v), 6)}
               for d, v in r.monthly.items()]

    charts = []
    for ch in r.charts:
        o = ch["ohlc"]
        charts.append({
            "symbol": ch["symbol"], "name": ch["name"],
            "dates": [str(d.date()) for d in o.index],
            # ECharts K 线的数据顺序：开、收、低、高
            "ohlc": [[round(float(a), 4), round(float(b), 4), round(float(c), 4), round(float(d), 4)]
                     for a, b, c, d in zip(o["open"], o["close"], o["low"], o["high"])],
            "lines": {k: _arr(v, 4) for k, v in ch["lines"].items()},
            "marks": ch["marks"],
        })

    fills = [
        {**{k: v for k, v in asdict(f).items() if k != "date"}, "date": str(f.date.date())}
        for f in r.fills[:MAX_FILLS]
    ]
    holdings = []
    if not r.positions.empty:
        last = r.positions[r.positions["date"] == r.positions["date"].max()]
        holdings = [
            {"symbol": row.symbol, "name": symbol_name(row.symbol), "qty": row.qty, "price": row.price,
             "value": row.value, "weight": row.weight, "contract": row.contract}
            for row in last.itertuples()
        ]

    payload = {
        "id": r.id, "kind": r.kind, "title": r.title, "strategy": r.strategy, "params": r.params,
        "universe": [{"symbol": u, "name": symbol_name(u)} for u in r.universe],
        "config": r.config, "metrics": r.metrics, "benchmarks": r.benchmarks,
        "series": {"dates": dates, "nav": _arr(s["nav"]), "drawdown": _arr(s["drawdown"]),
                   "exposure": _arr(s["exposure"], 4), "benchmarks": benches, "components": comps},
        "yearly": {"years": [int(y) for y in yearly.index],
                   "columns": {c: _arr(yearly[c]) for c in yearly.columns}},
        "monthly": monthly,
        "trades": [trade_to_dict(t) for t in r.trades],
        "fills": fills, "fills_truncated": len(r.fills) > MAX_FILLS, "fill_total": len(r.fills),
        "holdings_last": holdings,
        "charts": charts, "diagnostics": r.diagnostics, "warnings": r.warnings, "notes": r.notes,
        "components": r.components, "created_at": r.created_at, "elapsed": round(r.elapsed, 2),
    }
    return clean(payload)
