"""参数稳健性检验：参数网格 × 样本内 / 样本外，帮助学生识别过拟合。

做法：对 1 个或 2 个参数的每个取值组合做一次连续回测，把净值按"分割日"切成样本内（训练段）和
样本外（检验段），分别计算指标。然后回答三个教学问题：
1. 样本内表现最好的参数，到了样本外还好吗？（看它在样本外的排名）
2. 参数优劣在两段时间里是否一致？（样本内外指标的斯皮尔曼秩相关系数）
3. 哪组参数处在"高原"上？（与相邻参数一起平均后最好，比孤立的最高点更可信）
"""

from __future__ import annotations

import math
import time
from typing import Any

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .engine import metrics as M
from .strategies.base import ParamError, get_strategy_class

METRICS = {"sharpe": "夏普比率", "annual_return": "年化收益率", "max_drawdown": "最大回撤", "calmar": "卡玛比率"}
MAX_CELLS = 36
MIN_SEGMENT_DAYS = 60


def segment_metrics(nav: pd.Series) -> dict[str, float] | None:
    nav = nav.dropna()
    if len(nav) < MIN_SEGMENT_DAYS:
        return None
    nav = nav / nav.iloc[0]
    rets = nav.pct_change().dropna()
    ann = M.annual_return(nav)
    mdd = float(M.drawdown(nav).min())
    return {"total_return": M.total_return(nav), "annual_return": ann, "sharpe": M.sharpe_ratio(rets),
            "max_drawdown": mdd, "calmar": M.calmar_ratio(ann, mdd), "volatility": M.volatility(rets)}


def _clean(v: Any) -> Any:
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def run(strategy_id: str, base_params: dict[str, Any], universe: str | None, start: str, end: str,
        x_key: str, x_values: list[Any], y_key: str | None = None, y_values: list[Any] | None = None,
        split: str | None = None, metric: str = "sharpe", initial_capital: float | None = None) -> dict[str, Any]:
    t0 = time.perf_counter()
    cls = get_strategy_class(strategy_id)
    specs = {p["key"]: p for p in cls.param_specs()}
    if metric not in METRICS:
        raise ParamError(f"评价指标只能是 {', '.join(METRICS)}")
    for k in [x_key, y_key] if y_key else [x_key]:
        if k not in specs:
            raise ParamError(f"{cls.name} 没有参数 {k}（可用参数：{', '.join(specs)}）")
    if y_key == x_key:
        raise ParamError("两个参数不能相同")
    x_values = list(dict.fromkeys(x_values or []))
    y_values = list(dict.fromkeys(y_values or [])) if y_key else [None]
    if len(x_values) < 2 or (y_key and len(y_values) < 2):
        raise ParamError("每个参数至少要给 2 个取值")
    if len(x_values) * len(y_values) > MAX_CELLS:
        raise ParamError(f"参数组合最多 {MAX_CELLS} 个，当前 {len(x_values) * len(y_values)} 个，请减少取值")

    s, e = pd.Timestamp(start), pd.Timestamp(end)
    if e <= s:
        raise ParamError("结束日期必须晚于开始日期")
    split_ts = pd.Timestamp(split) if split else s + (e - s) * 0.7  # 默认前 70% 为样本内
    if not s < split_ts < e:
        raise ParamError("分割日必须在回测区间之内")
    cfg = {"start": start, "end": end}
    if initial_capital:
        cfg["initial_capital"] = initial_capital

    def evaluate(params: dict[str, Any]) -> dict[str, Any]:
        try:
            r = run_backtest(cls.id, params, universe or None, cfg)
        except ParamError as err:
            return {"ok": False, "error": str(err)}
        nav = r.series["nav"].iloc[1:]  # 去掉回测前一刻的起点
        train, test = segment_metrics(nav[nav.index < split_ts]), segment_metrics(nav[nav.index >= split_ts])
        if train is None or test is None:
            raise ParamError(f"样本内或样本外不足 {MIN_SEGMENT_DAYS} 个交易日，请调整分割日")
        full = segment_metrics(nav) or {}
        return {"ok": True, "full": full, "train": train, "test": test}

    cells = []
    for yv in y_values:
        for xv in x_values:
            params = {**base_params, x_key: xv, **({y_key: yv} if y_key else {})}
            cells.append({"x": xv, "y": yv, **evaluate(params)})
    default = evaluate(dict(base_params))

    # 高原：与相邻格子（含自身）一起平均后的样本内指标
    nx, ny = len(x_values), len(y_values)
    grid = np.full((ny, nx), np.nan)
    for i, c in enumerate(cells):
        if c["ok"]:
            grid[i // nx, i % nx] = c["train"][metric]
    for i, c in enumerate(cells):
        r, k = divmod(i, nx)
        win = grid[max(r - 1, 0):r + 2, max(k - 1, 0):k + 2]
        c["plateau"] = float(np.nanmean(win)) if c["ok"] and np.isfinite(win).any() else None

    ok = [c for c in cells if c["ok"]]
    if len(ok) < 2:
        raise ParamError("有效的参数组合不足 2 个（其余组合参数不合法），请调整取值")
    best = max(ok, key=lambda c: c["train"][metric])
    robust = max(ok, key=lambda c: c["plateau"])
    test_sorted = sorted(ok, key=lambda c: c["test"][metric], reverse=True)

    def pick(c: dict) -> dict:
        return {"x": c["x"], "y": c["y"], "train": c["train"], "test": c["test"],
                "test_rank": test_sorted.index(c) + 1 if c in test_sorted else None}

    tr = pd.Series([c["train"][metric] for c in ok])
    te = pd.Series([c["test"][metric] for c in ok])
    rho = float(tr.rank().corr(te.rank())) if len(ok) >= 3 else None  # 斯皮尔曼 = 秩的皮尔逊相关
    out = {
        "strategy": {"id": cls.id, "name": cls.name},
        "x": {"key": x_key, "title": specs[x_key]["title"], "values": x_values},
        "y": {"key": y_key, "title": specs[y_key]["title"], "values": y_values} if y_key else None,
        "metric": metric, "metric_label": METRICS[metric],
        "period": [start, end], "split": split_ts.strftime("%Y-%m-%d"),
        "cells": cells, "best_train": pick(best), "robust": pick(robust),
        "default": {"params": {x_key: base_params.get(x_key), **({y_key: base_params.get(y_key)} if y_key else {})},
                    "train": default.get("train"), "test": default.get("test")},
        "spearman": rho, "count": len(ok), "backtests": len(cells) + 1,
    }
    out["conclusions"] = conclusions(out)
    out["elapsed"] = time.perf_counter() - t0
    return _deep_clean(out)


def _deep_clean(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _deep_clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_deep_clean(v) for v in o]
    if isinstance(o, np.generic):
        return _clean(o.item())
    return _clean(o)


def _fmt(metric: str, v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}%" if metric in ("annual_return", "max_drawdown") else f"{v:.2f}"


def label(out: dict, c: dict) -> str:
    s = f"{out['x']['title']} {c['x']}"
    if out["y"]:
        s += f"、{out['y']['title']} {c['y']}"
    return s


def conclusions(out: dict) -> list[str]:
    m, n = out["metric"], out["count"]
    b, r = out["best_train"], out["robust"]
    lines = [f"样本内{out['metric_label']}最高的是「{label(out, b)}」（样本内 {_fmt(m, b['train'][m])}），"
             f"到了样本外是 {_fmt(m, b['test'][m])}，在 {n} 组参数中排第 {b['test_rank']}。"]
    if b["test_rank"] and b["test_rank"] > max(1, n // 2):
        lines.append("样本内最优的参数到样本外跌到了后一半，说明它很可能只是碰巧适合样本内那段行情——这就是过拟合。")
    elif b["test_rank"] and b["test_rank"] <= max(1, n // 4):
        lines.append("样本内最优的参数在样本外仍然靠前，这组参数的优势在两段时间里比较一致。")
    rho = out["spearman"]
    if rho is not None:
        if rho >= 0.5:
            desc = "参数的优劣排序在两段时间里比较一致，调参结论相对可信"
        elif rho > 0:
            desc = "参数的优劣排序在两段时间里只有微弱的一致性，不要过度相信最优值"
        else:
            desc = "参数的优劣排序在两段时间里几乎不一致甚至相反，按样本内结果挑参数基本没有意义"
        lines.append(f"样本内与样本外{out['metric_label']}的秩相关系数为 {rho:.2f}：{desc}。")
    if (r["x"], r["y"]) != (b["x"], b["y"]):
        lines.append(f"处在参数高原上的是「{label(out, r)}」（与相邻参数平均后最好），样本外 {_fmt(m, r['test'][m])}，"
                     f"排第 {r['test_rank']}。教学上更推荐选高原而不是孤立的最高点。")
    d = out["default"]
    if d.get("train") and d.get("test"):
        lines.append(f"作为对照，默认参数样本内 {_fmt(m, d['train'][m])}、样本外 {_fmt(m, d['test'][m])}。")
    lines.append("以上只说明这段历史中的表现，不代表未来；更严谨的做法是换多段时间重复检验（滚动样本外）。")
    return lines
