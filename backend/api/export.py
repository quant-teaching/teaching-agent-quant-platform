"""回测数据集导出：每日净值、量化指标、交易记录、成交明细、持仓明细等打包成 zip（CSV 用带 BOM 的 UTF-8，Excel 可直接打开）。"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from typing import Any

import pandas as pd

from quant.data.loader import symbol_name

from .services import get_entry, load_payload, result_path

DISCLAIMER = "本结果为教学回测模拟，历史回测不代表未来表现，不构成任何投资建议。"

METRICS = [
    ("total_return", "总收益率"), ("annual_return", "年化收益率"), ("volatility", "年化波动率"),
    ("sharpe", "夏普比率"), ("sortino", "索提诺比率"), ("max_drawdown", "最大回撤"), ("calmar", "卡玛比率"),
    ("max_drawdown_peak", "最大回撤高点"), ("max_drawdown_trough", "最大回撤谷底"),
    ("max_drawdown_recovery", "最大回撤恢复日"), ("max_drawdown_days", "最大回撤持续交易日"),
    ("trading_days", "交易日数"), ("best_day", "最佳单日收益"), ("worst_day", "最差单日收益"),
    ("positive_days_ratio", "上涨日占比"), ("trade_count", "交易次数（已平仓）"), ("open_trade_count", "未平仓交易"),
    ("win_rate", "胜率"), ("profit_loss_ratio", "盈亏比"), ("profit_factor", "利润因子"),
    ("avg_win", "平均盈利（元）"), ("avg_loss", "平均亏损（元）"), ("avg_holding_days", "平均持仓天数"),
    ("long_count", "多头交易次数"), ("short_count", "空头交易次数"), ("avg_gross_exposure", "平均仓位"),
    ("annual_turnover", "年化换手（倍）"), ("total_cost", "交易成本合计（元）"), ("cost_ratio", "交易成本 / 初始资金"),
    ("fill_count", "成交笔数"), ("initial_capital", "初始资金（元）"), ("final_equity", "期末权益（元）"),
]
BENCH_METRICS = [
    ("excess_annual_return", "超额年化收益"), ("beta", "β"), ("alpha", "α（年化）"),
    ("information_ratio", "信息比率"), ("tracking_error", "跟踪误差"), ("correlation", "相关系数"),
]


def _csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def _metrics_table(p: dict[str, Any]) -> pd.DataFrame:
    benches = [(c, p["benchmarks"][c]) for c in p["config"].get("benchmarks", []) if c in p["benchmarks"]]
    main = "组合" if p["kind"] == "portfolio" else "策略"
    rows = []
    for key, label in METRICS + BENCH_METRICS:
        row = {"指标": label, main: p["metrics"].get(key)}
        for _, b in benches:
            row[b["name"]] = b.get(key)
        if any(v is not None for k, v in row.items() if k != "指标"):
            rows.append(row)
    return pd.DataFrame(rows)


def _nav_table(p: dict[str, Any]) -> pd.DataFrame:
    s = p["series"]
    df = pd.DataFrame({"日期": s["dates"], "净值": s["nav"], "回撤": s["drawdown"], "仓位暴露": s["exposure"]})
    for label, v in s["components"].items():
        df[f"{label} 净值"] = v
    for code in p["config"].get("benchmarks", []):
        b = s["benchmarks"].get(code)
        if b:
            df[f"{b['name']} 净值"] = b["nav"]
            df[f"{b['name']} 回撤"] = b["drawdown"]
    return df


def _trades_table(p: dict[str, Any]) -> pd.DataFrame:
    cols = {"symbol": "代码", "name": "名称", "side": "方向", "entry_date": "开仓日", "exit_date": "平仓日",
            "entry_price": "平均开仓价", "exit_price": "平均平仓价", "max_qty": "最大持仓数量", "pnl": "净盈亏（元）",
            "cost": "手续费（元）", "return_pct": "收益率", "holding_days": "持仓天数", "is_open": "未平仓"}
    df = pd.DataFrame(p["trades"], columns=list(cols))
    df["is_open"] = df["is_open"].map({True: "是", False: "否"})
    return df.rename(columns=cols)


FILL_COLS = {"date": "日期", "symbol": "代码", "name": "名称", "action": "动作", "qty": "数量", "price": "成交价",
             "amount": "成交金额（元）", "fee": "手续费（元）", "slippage": "滑点成本（元）", "contract": "合约",
             "note": "备注"}


def _fills_table(p: dict[str, Any]) -> pd.DataFrame:
    path = result_path(p["id"]).with_name(f"{p['id']}.fills.parquet")
    if path.exists():  # 报告 JSON 里的成交明细有条数上限，完整明细单独存档
        df = pd.read_parquet(path)
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    else:
        df = pd.DataFrame(p["fills"])
    return df.reindex(columns=list(FILL_COLS)).rename(columns=FILL_COLS)


def _positions_table(p: dict[str, Any]) -> pd.DataFrame | None:
    path = result_path(p["id"]).with_name(f"{p['id']}.positions.parquet")
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df.insert(2, "name", df["symbol"].map(symbol_name))
    cols = {"date": "日期", "symbol": "代码", "name": "名称", "contract": "合约", "qty": "数量", "price": "收盘价",
            "value": "市值（元）", "weight": "占权益比例"}
    return df.reindex(columns=list(cols)).rename(columns=cols)


def _yearly_table(p: dict[str, Any]) -> pd.DataFrame:
    y = p["yearly"]
    return pd.DataFrame({"年份": y["years"], **y["columns"]})


def _param_lines(p: dict[str, Any]) -> list[str]:
    if p["kind"] == "portfolio":
        rb = {"none": "不调仓", "M": "每月", "Q": "每季度"}.get(p["params"].get("rebalance"), "")
        lines = [f"  {k}：{v:.0%}" for k, v in p["params"].get("weights", {}).items()]
        return lines + [f"  再平衡：{rb}"]
    try:
        specs = {s["key"]: s for s in get_entry(p["strategy"]["id"]).cls.param_specs()}
    except Exception:
        specs = {}
    out = []
    for k, v in p["params"].items():
        spec = specs.get(k, {})
        mark = "" if spec.get("default", v) == v else f"（默认 {spec['default']}）"
        out.append(f"  {spec.get('title', k)}（{k}）= {v}{mark}")
    return out


def _cost_lines(p: dict[str, Any]) -> list[str]:
    c, cat = p["config"], p["strategy"].get("category")
    out = []
    if cat != "futures":
        out.append(f"  A 股佣金 {c['stock_commission']:.4%}（最低 {c['stock_min_commission']:g} 元），"
                   f"卖出印花税 2023-08-28 前 0.1%、之后 0.05%，滑点 {c['stock_slippage']:.2%}，100 股一手，涨跌停开盘不可成交")
    if cat != "stock":
        out.append(f"  期货滑点 {c['futures_slippage_ticks']:g} 跳，手续费倍数 {c['futures_commission_scale']:g}，"
                   f"保证金占用上限 {c['max_margin_ratio']:.0%}，换月按收盘移仓并计费")
    return out


def _readme(p: dict[str, Any], files: list[tuple[str, str]]) -> str:
    c = p["config"]
    universe = "、".join(f"{u['name']}({u['symbol']})" for u in p["universe"])
    lines = [
        f"{p['title']} —— 回测数据集",
        "",
        f"⚠️ {DISCLAIMER}",
        "",
        f"回测编号：{p['id']}",
        f"生成时间：{p['created_at']}　导出时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"策略：{p['strategy']['name']} · {p['strategy'].get('style', '')}",
        f"回测区间：{c['start']} 至 {c['end']}",
        f"初始资金：{c['initial_capital']:,.0f} 元",
        f"标的（{len(p['universe'])} 个）：{universe}",
        "参数：",
        *_param_lines(p),
        "交易设置：",
        *_cost_lines(p),
        "  信号按 t 日收盘及之前的数据生成，t+1 日开盘成交",
        "",
        "文件说明：",
        *[f"  {name}：{desc}" for name, desc in files],
        "",
        "数值约定：收益率、回撤、权重、胜率等比例均为小数（0.1 表示 10%）；金额单位为元；",
        "净值起点为 1；期货市值为名义市值，负数表示空头。",
    ]
    if p["kind"] == "portfolio":
        lines.append("组合说明：各子策略按全部初始资金独立回测，组合净值按权重合成；交易记录与成交明细来自各子策略（备注列标明所属子策略），金额未按权重折算。")
    if p["warnings"]:
        lines += ["", "回测提示：", *[f"  {w}" for w in p["warnings"]]]
    return "\r\n".join(lines) + "\r\n"


def export_zip(result_id: str) -> tuple[str, bytes]:
    """返回（文件名, zip 字节）。"""
    p = load_payload(result_id)
    tables: list[tuple[str, str, pd.DataFrame]] = [
        ("量化指标.csv", "策略与各基准指数的全部量化指标", _metrics_table(p)),
        ("每日净值.csv", "每日净值、回撤、仓位暴露，以及子策略和基准指数的净值", _nav_table(p)),
        ("年度收益.csv", "每年收益率（首尾年份为区间内的部分年度）", _yearly_table(p)),
        ("月度收益.csv", "每月收益率", pd.DataFrame(p["monthly"]).rename(columns={"month": "月份", "ret": "收益率"})),
        ("交易记录.csv", "每笔完整交易（从开仓到平仓）的盈亏", _trades_table(p)),
        ("成交明细.csv", "每一笔成交（含加减仓、期货换月移仓）", _fills_table(p)),
    ]
    pos = _positions_table(p)
    if pos is not None:
        tables.append(("持仓明细.csv", "每个交易日收盘后的持仓", pos))
    files = [(name, desc) for name, desc, _ in tables] + [("report.json", "完整报告数据（平台内部格式）")]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("说明.txt", _readme(p, files).encode("utf-8-sig"))
        for name, _, df in tables:
            z.writestr(name, _csv(df))
        z.writestr("report.json", json.dumps(p, ensure_ascii=False, indent=1))
    safe = "".join(ch for ch in p["title"] if ch not in '\\/:*?"<>|+ ')[:40] or "回测"
    return f"{safe}_{p['config']['start']}_{p['config']['end']}.zip", buf.getvalue()
