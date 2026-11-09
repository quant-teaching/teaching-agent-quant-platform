"""用 LangGraph 编排一轮对话。四种工作模式共用一张状态图，按模式走不同的路线：

  自动执行   agent ⇄ tools                                  模型自己决定调用哪些工具
  每步确认   agent → approve（暂停等学生确认）→ tools → agent   学生逐个批准、修改或拒绝工具调用
  先计划     planner → review_plan（暂停等学生修改）→ execute_plan → summarize
                                                             学生决定做哪些步骤，模型只负责写计划和分析
  自主研究   research_plan → agent ⇄ tools → reflect →（未达成目标）agent …… → report
                                                             模型自己拆解目标、执行、反思评估、迭代

暂停用 LangGraph 的 interrupt()：图的状态保存在检查点里，学生在页面上确认后用 Command(resume=…) 继续。
模型调用仍走 llm.stream_chat（主备切换、额度、渠道权限不变）；工具执行前由 control.Control 强制检查学生的设置。
节点通过 get_stream_writer() 把文字片段、工具步骤等事件实时推给前端。
"""

from __future__ import annotations

import asyncio
import json
import operator
import re
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .control import ALL_TOOLS, Control, backtest_cost
from .tools import TOOL_LABELS, TOOLS, SessionState, Toolbox, ToolError

MAX_ROUNDS = 8  # 每轮（研究模式下每次迭代）最多的模型调用次数
BACKTEST_TOOLS = {"run_backtest", "run_portfolio_backtest", "compare_params", "robustness_test"}


class TurnState(TypedDict, total=False):
    mode: str
    control: dict
    session_id: str
    session_state: str  # SessionState 的 JSON：会话中修改过的参数、最近的回测
    messages: list[dict]  # 系统提示 + 历史 + 本轮用户输入
    turn_msgs: Annotated[list[dict], operator.add]  # 本轮新增的模型消息（工具调用与结果）
    events: Annotated[list[dict], operator.add]  # 保存到数据库、刷新页面后重现的卡片
    sources: Annotated[list, operator.add]  # 事实核验的数据来源
    pending: list[dict]  # 等待执行的工具调用 [{id, name, args, label}]
    pending_text: str
    decision: dict | None  # 学生对工具调用的确认结果
    plan: dict | None
    goal: dict | None  # 自主研究的目标与评判标准
    backtests: int
    rounds: int
    iteration: int
    ran_backtest: bool
    final: str
    model_used: str | None


def plain(x: Any) -> Any:
    """转成纯 JSON 数据再放进图状态（检查点只保存可序列化的数据）。"""
    return json.loads(json.dumps(x, ensure_ascii=False, default=str))


def tool_label(name: str, args: dict[str, Any]) -> str:
    base = TOOL_LABELS.get(name, name)
    target = args.get("strategy") or args.get("base") or args.get("query") or ""
    if name == "run_portfolio_backtest":
        target = " + ".join(str(c.get("strategy", "")) for c in args.get("components", []) if isinstance(c, dict))
    if args.get("start") and args.get("end"):
        target += f"（{args['start']} ~ {args['end']}）"
    return f"{base}：{target}" if target else base


def parse_json(text: str | None) -> Any:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------- 公共部分

async def call_llm(state: TurnState, config, extra: list[dict] | None = None, tools: list[dict] | None = None,
                   stream: bool = True):
    """调用模型，把模型切换、文字片段等事件推给前端。返回 (completion, 需要保存的事件, 模型名)。"""
    cfg = config["configurable"]
    writer = get_stream_writer()
    msgs = state["messages"] + state.get("turn_msgs", []) + (extra or [])
    completion, events, model = None, [], None
    async for ev in cfg["llm"](msgs, tools or None, prefer=cfg.get("model"), user=cfg.get("user")):
        if ev["type"] == "done":
            completion = ev["completion"]
            continue
        if ev["type"] == "model":
            model = ev["model"]
        elif ev["type"] == "switch":
            events.append({"kind": "model_switch", "from": ev["from"], "to": ev["to"], "reason": ev["reason"]})
        elif ev["type"] == "delta" and not stream:
            continue
        writer(ev)
    assert completion is not None
    return completion, events, model


def _phase(name: str, label: str, **extra) -> dict:
    """阶段标记：既推给前端，也保存进事件列表。"""
    ev = {"name": name, "label": label, **extra}
    get_stream_writer()({"type": "phase", **ev})
    return {"kind": "phase", **ev}


async def execute(box: Toolbox, ctl: Control, name: str, args: dict | None, used: int):
    """执行一个工具。返回 (结果, 卡片, 是否成功, 消耗的回测次数)。先检查学生的控制设置。"""
    if args is None:
        return {"error": "参数不是合法的 JSON，请重新生成"}, None, False, 0
    blocked = ctl.check(name, args, used)
    if blocked:
        return {"error": blocked, "blocked_by": "学生的控制设置"}, None, False, 0
    try:
        result, card = await asyncio.to_thread(box.call, name, args)
    except ToolError as e:
        return {"error": str(e)}, None, False, 0
    except Exception as e:  # 工具内部异常也反馈给模型，让它调整
        return {"error": f"{type(e).__name__}: {e}"}, None, False, 0
    result, card = ctl.filter_result(name, result, card)
    return result, card, True, backtest_cost(name, args)


async def run_calls(state: TurnState, calls: list[dict], text: str = "",
                    rejected: dict[str, str] | None = None) -> dict:
    """依次执行一组工具调用，产出前端事件，并整理成模型可读的消息。"""
    writer = get_stream_writer()
    ctl = Control.parse(state["control"])
    ss = SessionState.load(state.get("session_state", ""))
    box = Toolbox(ss, state["session_id"])
    used = state.get("backtests", 0)
    ran = state.get("ran_backtest", False)
    rejected = rejected or {}
    tool_calls, tool_msgs, events, sources = [], [], [], []
    for c in calls:
        name, args = c["name"], c.get("args")
        label = tool_label(name, args or {})
        tool_calls.append({"id": c["id"], "type": "function",
                           "function": {"name": name, "arguments": json.dumps(args or {}, ensure_ascii=False)}})
        writer({"type": "tool_start", "id": c["id"], "name": name, "label": label, "args": args})
        if c["id"] in rejected:
            why = rejected[c["id"]]
            result, card, ok, cost = {"error": "学生拒绝了这次调用" + (f"，理由：{why}" if why else "")}, None, False, 0
        else:
            result, card, ok, cost = await execute(box, ctl, name, args, used)
        used += cost
        ran = ran or (ok and name in BACKTEST_TOOLS)
        result = plain(result)
        sources.append({"_src": f"工具结果「{label}」", "data": result})
        tool_msgs.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result, ensure_ascii=False)})
        ev = {"id": c["id"], "name": name, "label": label, "ok": ok,
              "error": None if ok else result.get("error"), "card": plain(card) if card else None}
        writer({"type": "tool_end", **ev})
        events.append({"kind": "tool", **ev})
    return {"turn_msgs": [{"role": "assistant", "content": text, "tool_calls": tool_calls}, *tool_msgs],
            "events": events, "sources": sources, "session_state": ss.dump(), "backtests": used,
            "ran_backtest": ran, "pending": [], "pending_text": "", "decision": None}


def _tool_catalog(ctl: Control) -> str:
    """给"写计划"的模型看的工具清单（只含学生允许的工具）。"""
    lines = []
    for t in TOOLS:
        f = t["function"]
        if f["name"] not in ctl.tools:
            continue
        props = f["parameters"].get("properties", {})
        req = set(f["parameters"].get("required", []))
        def arg(k: str, v: dict, req: set = req) -> str:
            notes = ["必填"] if k in req else []
            if v.get("enum"):
                notes.append("可选值 " + "/".join(map(str, v["enum"])))
            return k + (f"（{'，'.join(notes)}）" if notes else "")
        args = "、".join(arg(k, v) for k, v in props.items()) or "无"
        lines.append(f"- {f['name']}：{f['description']}。参数：{args}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 自动执行 / 每步确认

async def agent_node(state: TurnState, config) -> dict:
    ctl = Control.parse(state["control"])
    rounds = state.get("rounds", 0) + 1
    exclude = BACKTEST_TOOLS if state.get("backtests", 0) >= ctl.max_backtests else set()
    tools = ctl.tool_specs(exclude) if rounds < MAX_ROUNDS else []
    extra = [] if tools or rounds < MAX_ROUNDS else [
        {"role": "system", "content": "工具调用次数已达上限，请直接基于已有结果给出结论。"}]
    comp, events, model = await call_llm(state, config, extra, tools)
    upd: dict[str, Any] = {"rounds": rounds, "events": events, "model_used": model or state.get("model_used")}
    if comp.tool_calls and tools:
        calls = []
        for c in comp.tool_calls:
            try:
                args = json.loads(c.arguments or "{}")
                args = args if isinstance(args, dict) else None
            except json.JSONDecodeError:
                args = None
            calls.append({"id": c.id, "name": c.name, "args": plain(args), "label": tool_label(c.name, args or {})})
        if comp.content:
            get_stream_writer()({"type": "round_text_end"})
        upd.update(pending=calls, pending_text=comp.content or "", decision=None)
    else:
        upd.update(pending=[], final=comp.content or "")
        if state["mode"] == "research":  # 本次迭代的小结留给反思节点参考
            upd["turn_msgs"] = [{"role": "assistant", "content": comp.content or ""}]
    return upd


def after_agent(state: TurnState) -> str:
    if state.get("pending"):
        return "approve" if state["mode"] == "confirm" else "tools"
    return "reflect" if state["mode"] == "research" else END


def approve_node(state: TurnState) -> dict:
    """每步确认：暂停，等学生逐个批准、修改参数或拒绝。interrupt 之前不能有副作用（恢复时本节点会重跑）。"""
    calls = state["pending"]
    decision = interrupt({"kind": "tools", "text": state.get("pending_text", ""),
                          "calls": [{**c, "tool": TOOL_LABELS.get(c["name"], c["name"])} for c in calls]}) or {}
    per = decision.get("calls") or {}
    items, new_calls, rejected = [], [], {}
    for c in calls:
        d = per.get(c["id"]) or {}
        action = "reject" if decision.get("action") == "reject_all" else d.get("action", "approve")
        args = d.get("args") if isinstance(d.get("args"), dict) else c["args"]
        edited = action != "reject" and args != c["args"]
        if action == "reject":
            rejected[c["id"]] = str(decision.get("feedback") or "")
        new_calls.append({**c, "args": plain(args)})
        items.append({"label": tool_label(c["name"], args or {}),
                      "action": "rejected" if action == "reject" else "edited" if edited else "approved"})
    feedback = str(decision.get("feedback") or "").strip()
    record = {"kind": "approval", "type": "tools", "status": "done", "items": items, "feedback": feedback}
    get_stream_writer()({**record, "type": "approval_done", "approval_type": "tools"})  # interrupt 之后才推送，重跑不会重复
    return {"pending": new_calls, "decision": {"rejected": rejected, "feedback": feedback}, "events": [record]}


async def tools_node(state: TurnState) -> dict:
    dec = state.get("decision") or {}
    upd = await run_calls(state, state["pending"], state.get("pending_text", ""), dec.get("rejected"))
    if dec.get("feedback"):
        upd["turn_msgs"].append({"role": "user", "content": f"（我在确认这一步时补充）{dec['feedback']}"})
    return upd


# ---------------------------------------------------------------- 先计划后执行

PLAN_PROMPT = """现在不要直接调用工具。请为学生的请求写一份可执行的计划，交给学生审核修改后由程序按顺序执行。
可用的工具（只能用这些）：
{tools}

只输出一个 JSON 对象，不要输出其他文字：
{{"intro": "一两句话说明计划思路",
  "steps": [{{"tool": "工具名", "args": {{参数}}, "why": "这一步为什么要做（一句话）"}}]}}
要求：
- 最多 8 步，按执行顺序排列；参数写完整、具体，策略用算法库中的 id，日期用 YYYY-MM-DD；
- 学生没给回测区间时用 2022-01-01 至 2025-12-31；
- 改参数后再回测时，先用 update_params，再用 run_backtest；
- 需要查看上一次回测的细节时，get_backtest_detail 的 result_id 写 "$last"；
- 纯概念问题可以只用 search_knowledge 或 get_strategy。"""


async def planner_node(state: TurnState, config) -> dict:
    ctl = Control.parse(state["control"])
    get_stream_writer()({"type": "phase", "name": "planning", "label": "正在制定计划"})
    comp, events, model = await call_llm(
        state, config, [{"role": "system", "content": PLAN_PROMPT.format(tools=_tool_catalog(ctl))}], stream=False)
    data = parse_json(comp.content) or {}
    steps = []
    for s in (data.get("steps") or [])[:10]:
        if not isinstance(s, dict) or s.get("tool") not in ALL_TOOLS or s["tool"] not in ctl.tools:
            continue
        args = s.get("args") if isinstance(s.get("args"), dict) else {}
        steps.append({"tool": s["tool"], "args": plain(args), "why": str(s.get("why") or "")[:200]})
    upd: dict[str, Any] = {"events": events, "model_used": model}
    if not steps:
        upd.update(plan=None, final=comp.content if comp.content and not data else
                   "这次没能生成可执行的计划。可以把需求说得更具体一些（例如策略名、回测区间），或换成「自动执行」模式。")
    else:
        upd["plan"] = {"intro": str(data.get("intro") or ""), "steps": steps}
    return upd


def review_plan_node(state: TurnState) -> dict:
    plan = state["plan"]
    decision = interrupt({"kind": "plan", "intro": plan["intro"],
                          "steps": [{**s, "label": tool_label(s["tool"], s["args"]),
                                     "tool_label": TOOL_LABELS.get(s["tool"], s["tool"])} for s in plan["steps"]]}) or {}
    writer = get_stream_writer()
    if decision.get("action") == "cancel":
        record = {"kind": "approval", "type": "plan", "status": "cancelled", "items": []}
        writer({**record, "type": "approval_done", "approval_type": "plan"})
        return {"plan": None, "final": "好的，已取消这个计划。你可以调整需求后重新发给我，或换一种工作模式。",
                "events": [record]}
    steps = []
    for s in decision.get("steps") or plan["steps"]:
        if isinstance(s, dict) and s.get("tool") in ALL_TOOLS:
            steps.append({"tool": s["tool"], "args": plain(s.get("args") if isinstance(s.get("args"), dict) else {}),
                          "why": str(s.get("why") or "")})
    items = [{"label": tool_label(s["tool"], s["args"]), "action": "approved"} for s in steps]
    edited = steps != plan["steps"]
    shown = [{**s, "tool_label": TOOL_LABELS.get(s["tool"], s["tool"])} for s in steps]
    record = {"kind": "approval", "type": "plan", "status": "done", "edited": edited, "items": items}
    plan_ev = {"kind": "plan", "intro": plan["intro"], "steps": shown}
    writer({**record, "type": "approval_done", "approval_type": "plan"})
    writer({**plan_ev, "type": "plan"})
    return {"plan": {**plan, "steps": steps}, "events": [record, plan_ev]}


def after_review(state: TurnState) -> str:
    return "execute_plan" if state.get("plan") and state["plan"]["steps"] else END


async def execute_plan_node(state: TurnState) -> dict:
    ss = SessionState.load(state.get("session_state", ""))
    acc: dict[str, Any] = {"turn_msgs": [], "events": [], "sources": []}
    cur = dict(state)
    for i, s in enumerate(state["plan"]["steps"]):
        args = s["args"]
        if any(v == "$last" for v in args.values()):  # 引用上一步回测的结果
            ss = SessionState.load(cur.get("session_state", ""))
            last = ss.results[-1]["id"] if ss.results else None
            args = {k: (last if v == "$last" else v) for k, v in args.items()}
        upd = await run_calls(cur, [{"id": f"plan{i + 1}", "name": s["tool"], "args": args}])
        for k in ("turn_msgs", "events", "sources"):
            acc[k] += upd[k]
            cur[k] = cur.get(k, []) + upd[k]
        for k in ("session_state", "backtests", "ran_backtest"):
            acc[k] = cur[k] = upd[k]
    return acc


SUMMARY_PROMPT = "以上是学生审核并确认后、按计划依次执行的工具结果。请不要再调用工具，按回复格式分析结果；某一步失败的，说明原因和可以怎么调整。"


async def summarize_node(state: TurnState, config) -> dict:
    comp, events, model = await call_llm(state, config, [{"role": "system", "content": SUMMARY_PROMPT}])
    return {"final": comp.content or "", "events": events, "model_used": model or state.get("model_used")}


# ---------------------------------------------------------------- 自主研究

RESEARCH_PROMPT = """学生选择了「自主研究」模式：你要自己拆解学生的研究目标、设计并执行实验、根据结果反思并迭代。
先不要调用工具，只输出一个 JSON 对象，不要输出其他文字：
{"goal": "用一句话重述研究目标", "criteria": "怎样算达成目标（尽量可量化，如最大回撤小于 15%、夏普高于沪深 300）",
 "steps": ["第一轮准备做的实验 1", "实验 2", "……（2~5 条）"]}"""

REFLECT_PROMPT = """现在是第 {i} 轮实验后的反思（最多 {n} 轮，已用回测 {used}/{budget} 次）。
研究目标：{goal}
达成标准：{criteria}
根据上面工具返回的真实结果判断目标是否已经达成。只输出一个 JSON 对象，不要输出其他文字：
{{"goal_met": true 或 false, "assessment": "用工具结果里的数字说明当前进展（原样引用数字）",
  "next": "如果没达成，下一轮具体做什么（换哪个策略、改哪个参数到多少、为什么）；达成了就写空字符串"}}"""

REPORT_PROMPT = """研究结束。请写一份给学生的研究报告，结构：
**【研究目标】** 目标与达成标准
**【研究过程】** 每一轮做了什么实验、得到什么结果（数字照抄工具结果）
**【结论】** 是否达成目标；最终推荐用于继续学习的策略和参数，以及它在历史上的表现
**【反思与局限】** 过拟合风险、样本区间、幸存者偏差等；建议学生自己再做的验证实验
不要再调用工具。"""


async def research_plan_node(state: TurnState, config) -> dict:
    get_stream_writer()({"type": "phase", "name": "planning", "label": "正在拆解研究目标"})
    comp, events, model = await call_llm(state, config, [{"role": "system", "content": RESEARCH_PROMPT}], stream=False)
    data = parse_json(comp.content) or {}
    goal = {"goal": str(data.get("goal") or "完成学生提出的研究任务"), "criteria": str(data.get("criteria") or "由智能体根据结果判断"),
            "steps": [str(x) for x in (data.get("steps") or []) if x][:6]}
    plan_ev = _phase("research_plan", "研究计划", **goal)
    start_ev = _phase("iteration", "第 1 轮 · 执行实验", iteration=1)
    steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(goal["steps"]))
    note = (f"【研究计划】目标：{goal['goal']}；达成标准：{goal['criteria']}。第 1 轮计划：\n{steps}\n"
            "现在开始执行第 1 轮：调用工具完成这些实验，完成后用两三句话小结本轮结果（不要写最终报告）。")
    return {"goal": goal, "iteration": 1, "rounds": 0, "events": [*events, plan_ev, start_ev], "model_used": model,
            "turn_msgs": [{"role": "system", "content": note}]}


async def reflect_node(state: TurnState, config) -> dict:
    ctl = Control.parse(state["control"])
    i, goal = state.get("iteration", 1), state.get("goal") or {}
    get_stream_writer()({"type": "phase", "name": "reflecting", "label": f"第 {i} 轮 · 正在反思"})
    prompt = REFLECT_PROMPT.format(i=i, n=ctl.max_iterations, used=state.get("backtests", 0),
                                   budget=ctl.max_backtests, goal=goal.get("goal"), criteria=goal.get("criteria"))
    comp, events, _ = await call_llm(state, config, [{"role": "system", "content": prompt}], stream=False)
    data = parse_json(comp.content) or {"goal_met": True, "assessment": comp.content or "", "next": ""}
    met = bool(data.get("goal_met"))
    out_of_budget = state.get("backtests", 0) >= ctl.max_backtests
    stop = met or i >= ctl.max_iterations or out_of_budget
    reason = "目标已达成" if met else "已达到最多迭代轮数" if i >= ctl.max_iterations else \
        "回测次数已用完" if out_of_budget else ""
    ref_ev = _phase("reflect", f"第 {i} 轮 · 反思", iteration=i, goal_met=met,
                    assessment=str(data.get("assessment") or ""), next=str(data.get("next") or ""), stop_reason=reason)
    upd: dict[str, Any] = {"events": [*events, ref_ev], "sources": [{"_src": f"第 {i} 轮反思", "data": plain(data)}],
                           "turn_msgs": [{"role": "system", "content": f"【第 {i} 轮反思】{json.dumps(data, ensure_ascii=False)}"}]}
    if not stop:
        upd["events"].append(_phase("iteration", f"第 {i + 1} 轮 · 执行实验", iteration=i + 1))
        upd["turn_msgs"].append({"role": "system", "content": f"开始第 {i + 1} 轮：按反思中的下一步执行实验，完成后用两三句话小结本轮结果。"})
        upd.update(iteration=i + 1, rounds=0)
    else:
        upd["iteration"] = i
    return upd


def _stopped(state: TurnState) -> bool:
    last = next((e for e in reversed(state.get("events", [])) if e.get("kind") == "phase"), {})
    return last.get("name") == "reflect"  # 反思后没有开启新一轮，说明要结束


async def report_node(state: TurnState, config) -> dict:
    _ev = _phase("report", "撰写研究报告")
    comp, events, model = await call_llm(state, config, [{"role": "system", "content": REPORT_PROMPT}])
    return {"final": comp.content or "", "events": [_ev, *events], "model_used": model or state.get("model_used")}


# ---------------------------------------------------------------- 组装

def start_route(state: TurnState) -> str:
    return {"plan": "planner", "research": "research_plan"}.get(state["mode"], "agent")


def build_graph():
    g = StateGraph(TurnState)
    g.add_node("agent", agent_node)
    g.add_node("approve", approve_node)
    g.add_node("tools", tools_node)
    g.add_node("planner", planner_node)
    g.add_node("review_plan", review_plan_node)
    g.add_node("execute_plan", execute_plan_node)
    g.add_node("summarize", summarize_node)
    g.add_node("research_plan", research_plan_node)
    g.add_node("reflect", reflect_node)
    g.add_node("report", report_node)
    g.add_conditional_edges(START, start_route, ["agent", "planner", "research_plan"])
    g.add_conditional_edges("agent", after_agent, ["approve", "tools", "reflect", END])
    g.add_edge("approve", "tools")
    g.add_edge("tools", "agent")
    g.add_conditional_edges("planner", lambda s: "review_plan" if s.get("plan") else END, ["review_plan", END])
    g.add_conditional_edges("review_plan", after_review, ["execute_plan", END])
    g.add_edge("execute_plan", "summarize")
    g.add_edge("summarize", END)
    g.add_edge("research_plan", "agent")
    g.add_conditional_edges("reflect", lambda s: "report" if _stopped(s) else "agent", ["report", "agent"])
    g.add_edge("report", END)
    return g.compile(checkpointer=InMemorySaver())


GRAPH = build_graph()
