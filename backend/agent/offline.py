"""离线兜底：云端大模型都不可用（断网、没配置、接口故障）时，平台仍然可以完成核心操作。

不使用任何模型：用规则从学生的话里解析出策略、日期、参数修改、组合等意图，直接调用与智能体相同的工具，
再把工具返回的真实结果按模板整理成回复（数字照抄工具结果，同样经过事实核验）。
对外表现为一个和 llm.stream_chat 相同格式的事件流，智能体编排无需区分。
"""
from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

from quant.strategies.resolve import match_strategies

from .llm import Completion, ToolCall

DEFAULT_START, DEFAULT_END = "2022-01-01", "2025-12-31"
FEEDBACK_PREFIX = "（我在确认这一步时补充）"


# ---------------------------------------------------------------- 解析学生的话

def _last_user(messages: list[dict]) -> tuple[int, str]:
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if m.get("role") == "user" and not str(m.get("content", "")).startswith(FEEDBACK_PREFIX):
            return i, str(m.get("content", ""))
    return -1, ""


def parse_strategies(text: str) -> list[str]:
    if "组合" in text:  # "等权组合""自定义权重组合"说的是组合方式，不是「等权定期再平衡」策略
        text = re.sub(r"等权(重)?|平均分配|做组合|组合", " ", text)
    found: list[str] = []
    for seg in re.split(r"[和与、+＋，,；;及]|以及|还有", text):
        hits = match_strategies(seg.strip())
        if hits and hits[0][1] >= 50 and hits[0][0].id not in found:
            found.append(hits[0][0].id)
    if not found:
        hits = match_strategies(text)
        if hits and hits[0][1] >= 50:
            found.append(hits[0][0].id)
    return found


def parse_dates(text: str) -> tuple[str, str] | None:
    full = re.findall(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if len(full) >= 2:
        (y1, m1, d1), (y2, m2, d2) = full[0], full[1]
        return f"{y1}-{int(m1):02d}-{int(d1):02d}", f"{y2}-{int(m2):02d}-{int(d2):02d}"
    years = re.findall(r"(20\d{2})\s*年?", text)
    if len(years) >= 2:
        return f"{years[0]}-01-01", f"{years[1]}-12-31"
    if len(years) == 1:
        return f"{years[0]}-01-01", f"{years[0]}-12-31"
    return None


def parse_param_changes(text: str, strategy_id: str) -> dict[str, Any]:
    """识别"ATR 周期改为 22""仓位上限 0.15""fast=5"这类说法，按参数中文名或键名匹配。"""
    from api import services
    try:
        specs = services.get_entry(strategy_id).info()["params"]
    except Exception:
        return {}
    out: dict[str, Any] = {}
    pattern = r"([A-Za-z_一-龥 ]{1,14}?)\s*(?:改为|改成|设为|设置为|设成|调到|调为|调整为|=|：|:|为)?\s*(-?\d+(?:\.\d+)?)"
    for name, val in re.findall(pattern, text):
        name = name.strip().replace(" ", "")
        if not name or re.fullmatch(r"\d+", name):
            continue
        best, score = None, 0.0
        for p in specs:
            title = p["title"].replace(" ", "")
            if name.lower() == p["key"].lower():
                best, score = p, 2.0
                break
            common = len(set(name) & set(title))
            s = common / max(len(set(title)), 1)
            if common >= 2 and s > score:
                best, score = p, s
        if best and score >= 0.5 and best["type"] in ("integer", "number"):
            v: Any = float(val)
            if best["type"] == "integer":
                v = int(round(v))
            out[best["key"]] = v
    return out


def plan_calls(text: str, tools: set[str]) -> tuple[list[tuple[str, dict]], str]:
    """根据学生的话决定要调用的工具。返回 (调用列表, 说明)。"""
    strategies = parse_strategies(text)
    dates = parse_dates(text)
    start, end = dates or (DEFAULT_START, DEFAULT_END)
    universe = None
    codes = re.findall(r"\b\d{6}\b", text)
    if codes:
        universe = ",".join(codes)
    elif "行业" in text and "轮动" not in text:
        universe = "industries"
    wants_bt = any(k in text for k in ("回测", "测一下", "跑一下", "测试", "表现", "收益", "回撤")) or bool(dates)
    calls: list[tuple[str, dict]] = []
    note = ""
    if any(k in text for k in ("有哪些", "有什么策略", "有什么算法", "算法库", "策略列表")) and not strategies:
        calls.append(("list_strategies", {}))
    elif "组合" in text and len(strategies) >= 2:
        calls.append(("run_portfolio_backtest", {"components": [{"strategy": s} for s in strategies[:8]],
                                                 "start": start, "end": end}))
    elif strategies and wants_bt:
        sid = strategies[0]
        changes = parse_param_changes(text, sid)
        if changes:
            calls.append(("update_params", {"strategy": sid, "changes": changes}))
        args = {"strategy": sid, "start": start, "end": end}
        if universe:
            args["universe"] = universe
        calls.append(("run_backtest", args))
        if not dates:
            note = f"你没有指定回测区间，默认使用 {DEFAULT_START} 至 {DEFAULT_END}。"
    elif strategies:
        calls.append(("get_strategy", {"strategy": strategies[0]}))
    elif text.strip():
        calls.append(("search_knowledge", {"query": text.strip()[:100]}))
    allowed = [(n, a) for n, a in calls if n in tools]
    if len(allowed) < len(calls):
        note += "部分操作被「智能体控制」中的设置禁用，已跳过。"
    return allowed, note


# ---------------------------------------------------------------- 根据工具结果写回复（模板）

def _table(rows: list[tuple[str, Any]]) -> str:
    return "| 指标 | 数值 |\n|---|---:|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows if v is not None)


def describe(name: str, args: dict, r: dict) -> str:
    if "error" in r:
        return f"**{name}** 没有成功：{r['error']}"
    if name == "update_params":
        ch = "；".join(f"{c['title']} {c['old']} → {c['new']}" for c in r.get("changes", [])) or "参数没有变化"
        return f"**【参数修改】** {r.get('strategy', '')}：{ch}"
    if name == "run_backtest":
        m, b = r["metrics"], r.get("benchmarks", {})
        hs = b.get("沪深300") or next(iter(b.values()), {})
        lines = [f"**【回测】** {r['title']}，区间 {r['period']}，标的 {r.get('universe_size')} 个。",
                 _table([(k, m.get(k)) for k in ("总收益率", "年化收益率", "最大回撤", "夏普比率", "卡玛比率",
                                                  "年化波动率", "胜率", "盈亏比", "交易次数", "交易成本占初始资金")])]
        if hs:
            lines.append(f"**【基准对比】** 沪深 300 同期年化收益率 {hs.get('年化收益率')}、最大回撤 {hs.get('最大回撤')}；"
                         f"策略年化超额 {hs.get('策略年化超额')}。")
        reg = next((v for k, v in r.get("diagnostics", {}).items() if k.startswith("行情分段")), None)
        if isinstance(reg, dict) and reg:
            lines.append("**【行情分段】** " + "；".join(f"{k}：{v}" if not isinstance(v, dict) else
                                                     f"{k}：" + "，".join(f"{a} {b}" for a, b in v.items())
                                                     for k, v in reg.items()))
        win, plr = m.get("胜率") or "", m.get("盈亏比") or ""
        try:
            if float(win.rstrip("%")) < 45 and float(plr) > 1.3:
                lines.append(f"胜率 {win} 不高、盈亏比 {plr} 较高，是典型的趋势跟踪特征：多数交易小亏，靠少数大趋势盈利。")
        except ValueError:
            pass
        return "\n\n".join(lines)
    if name == "run_portfolio_backtest":
        comps = r.get("components", [])
        div = r.get("diversification", {})
        rows = "\n".join(f"| {c['name']} | {c.get('weight')} | {c.get('annual_return')} | {c.get('max_drawdown')} | {c.get('sharpe')} |"
                         for c in comps)
        m = r["metrics"]
        return (f"**【组合回测】** {r['title']}，区间 {r['period']}\n\n"
                f"| 对象 | 权重 | 年化收益率 | 最大回撤 | 夏普 |\n|---|---:|---:|---:|---:|\n"
                f"| **组合** | 100% | {m.get('年化收益率')} | {m.get('最大回撤')} | {m.get('夏普比率')} |\n{rows}\n\n"
                f"**【分散化】** 子策略平均相关系数 {div.get('平均相关系数')}，分散化比率 {div.get('分散化比率')}。"
                "相关系数越低、分散化比率越高，组合的分散效果越好。")
    if name == "get_strategy":
        doc = r.get("doc", {})
        parts = [f"**【{r['name']}】** {r.get('category')} · {r.get('style')}\n\n{r.get('summary', '')}"]
        for k in ("一句话理解", "原理", "什么行情好用，什么行情吃亏"):
            if doc.get(k):
                parts.append(f"**{k}**\n\n{doc[k][:700]}")
        ps = "、".join(f"{p['title']}（{p['key']}，当前 {p['current']}）" for p in r.get("params", []))
        parts.append(f"**可调参数**：{ps}")
        return "\n\n".join(parts)
    if name == "search_knowledge":
        res = r.get("results", [])[:2]
        if not res:
            return "知识库里没有找到相关内容。"
        return "\n\n".join(f"**{x['来源']}**\n\n{x['内容'][:600]}" for x in res)
    if name == "list_strategies":
        items = r.get("strategies", [])
        stock = "、".join(i["name"] for i in items if i["category"] == "股票")
        fut = "、".join(i["name"] for i in items if i["category"] == "期货")
        return f"算法库共 {r.get('count')} 个策略。\n\n**股票**：{stock}\n\n**期货**：{fut}"
    return json.dumps(r, ensure_ascii=False)[:800]


HELP = ("当前处于**离线模式**（没有连接到大模型），我可以按规则完成这些操作：\n\n"
        "- 回测：\"用双均线策略回测 2022-01-01 到 2024-12-31\"\n"
        "- 改参数后回测：\"海龟策略 ATR 周期改为 22，回测 2021 到 2024\"\n"
        "- 组合：\"双均线和动量选股做组合，回测 2022 到 2025\"\n"
        "- 讲解策略：\"讲讲布林带策略\"；查看算法库：\"有哪些策略\"\n\n"
        "连上云端大模型后，可以进行更自由的对话和分析。")


# ---------------------------------------------------------------- 事件流

def _chunks(text: str, n: int = 24):
    for i in range(0, len(text), n):
        yield text[i:i + n]


async def rule_stream(messages: list[dict], tools: list[dict] | None = None, reason: str = "") -> AsyncIterator[dict]:
    """与 llm.stream_chat 相同格式的事件流。"""
    label = "离线规则助手"
    yield {"type": "model", "provider": "离线", "model": label, "fallback": True}
    idx, text = _last_user(messages)
    after = messages[idx + 1:] if idx >= 0 else []
    tool_msgs = [m for m in after if m.get("role") == "tool"]
    names = {t["function"]["name"] for t in tools or []}

    if not tool_msgs and names:  # 第一轮：决定调用哪些工具
        calls, note = plan_calls(text, names)
        if calls:
            yield {"type": "done", "completion": Completion(
                content=note, model=label, provider="离线",
                tool_calls=[ToolCall(id=f"off{i}", name=n, arguments=json.dumps(a, ensure_ascii=False))
                            for i, (n, a) in enumerate(calls)])}
            return

    # 第二轮：根据工具结果写回复
    called = {}
    for m in after:
        for c in m.get("tool_calls") or []:
            called[c["id"]] = (c["function"]["name"], json.loads(c["function"].get("arguments") or "{}"))
    results = []
    for m in tool_msgs:
        name, args = called.get(m.get("tool_call_id"), ("工具", {}))
        try:
            results.append((name, args, json.loads(m.get("content") or "{}")))
        except json.JSONDecodeError:
            continue
    head = ("> [!NOTE] 离线模式\n> 当前没有连接到云端大模型" + (f"（{reason}）" if reason else "")
            + "，以下由平台规则助手调用工具，并根据真实结果整理。\n\n")
    body = "\n\n".join(describe(n, a, r) for n, a, r in results) if results else HELP
    content = head + body
    for piece in _chunks(content):
        yield {"type": "delta", "text": piece}
    yield {"type": "done", "completion": Completion(content=content, model=label, provider="离线")}
