"""对话智能体：调度层。解析用户的自然语言 → 调用算法库、回测引擎、知识库工具 → 基于工具结果做教学分析。

一轮对话由 graph.py 中的 LangGraph 状态图编排，支持四种工作模式（自动执行、每步确认、先计划后执行、自主研究）；
需要学生确认时图会暂停，确认结果通过 resume_turn 送回后继续执行。

三道保障：
1. 免责：本轮只要执行过回测，回复末尾由程序追加免责声明，不依赖模型自觉；
2. 合规：识别寻求实盘投资建议的提问，提示模型拒绝并引导回教学；
3. 防编造：回复中出现的百分数和小数必须能在工具结果、用户输入或系统信息中找到，否则标记为"未核验"。
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

from langgraph.types import Command
from sqlmodel import Session, select

from api import services
from api.db import ChatMessage, ChatSession, engine, now
from quant.data.catalog import FUTURES
from quant.strategies.base import load_all

from .control import Control
from .graph import GRAPH, plain
from .graph import tool_label as _tool_label  # noqa: F401  兼容旧的导入位置
from .llm import LLMError, ModelRef, stream_chat
from .tools import SessionState, today

HISTORY_TURNS = 10
TOOL_RESULT_HISTORY_CHARS = 2500

ADVICE_PATTERNS = [
    r"(买|卖|入手|抄底|加仓|减仓|清仓).{0,6}(哪|什么|哪些|哪只|哪个)",
    r"(推荐|建议).{0,8}(股票|个股|基金|合约|标的|买入|卖出)",
    r"(明天|下周|后市|未来|接下来|今年).{0,8}(涨|跌|走势|行情|能到)",
    r"(能不能|可不可以|该不该|要不要|值不值得).{0,6}(买|卖|入|持有|上车)",
    r"目标价|实盘.{0,4}(怎么|如何)?操作|现在.{0,4}(买|卖)",
]


def wants_investment_advice(text: str) -> bool:
    return any(re.search(p, text) for p in ADVICE_PATTERNS)


def system_prompt(state: SessionState) -> str:
    reg = load_all()
    ov = services.market_overview()
    ranges = ov["ranges"]
    lines = []
    for e in services.catalog():
        tag = "衍生" if e.get("derived") else e["category_label"]
        lines.append(f"- {e['id']}｜{e['name']}｜{tag}｜{e['style']}")
    working = []
    for sid, params in state.params.items():
        if params:
            try:
                name = services.get_entry(sid).name
            except services.NotFound:
                continue
            working.append(f"- {name}（{sid}）：{json.dumps(params, ensure_ascii=False)}")
    recent = [f"- {r['id']}｜{r['title']}｜{r['period']}" for r in state.results[-5:]]
    futures = "、".join(f"{f.code} {f.name}" for f in FUTURES)
    rng = lambda k: f"{ranges[k][0]} 至 {ranges[k][1]}" if k in ranges else "暂无"  # noqa: E731
    return f"""你是「量化策略教学助手」，运行在一个面向教学的量化策略回测平台中，帮助学生学习量化交易算法：调取算法库中的策略、讲解原理、修改参数、执行历史回测、解读回测报告、给出带原理说明的参数优化建议、构建多策略组合并分析分散化效果。

# 平台信息
- 今天是 {today()}。
- 数据范围：A 股与申万行业 {rng('stock')}；商品期货主力连续合约 {rng('futures')}（由单合约按持仓量自建）。
- 标的池：stock_pool＝教学股票池（55 只沪深 300 各行业龙头，"沪深 A 股""A 股"都指它）；industries＝31 个申万一级行业指数；futures＝{len(FUTURES)} 个商品期货品种（"商品期货主力合约""国内期货"都指它）：{futures}。也可以用逗号分隔的具体代码。
- 回测默认设置：初始资金 1000 万元；A 股佣金万分之 2.5（最低 5 元）、卖出印花税（2023-08-28 前 0.1%，之后 0.05%）、滑点 0.05%、100 股一手、涨跌停不可成交；期货按成交额约万分之 1 收手续费、滑点 1 跳、换月移仓计费、保证金占用上限 80%；信号收盘生成、次日开盘成交；基准为沪深 300、中证 500、创业板指。
- 算法库共 {len(reg)} 个内置策略（另含用户衍生策略），格式 id｜名称｜类别｜风格：
{chr(10).join(lines)}
- 当前会话中修改过的参数：
{chr(10).join(working) if working else '（无）'}
- 本会话最近的回测：
{chr(10).join(recent) if recent else '（无）'}

# 工作方式
1. 用户提到某个策略时，用 get_strategy 调取（它能识别"海龟""布林带股票""MACD 金叉死叉"等说法）。要修改参数时用 update_params，参数键名必须用 get_strategy 返回的 key；回复时列出"原参数 → 新参数"。
2. 用户要求回测时调用 run_backtest。用户没给时间区间时，使用 2022-01-01 至 2025-12-31 并告诉用户；没给标的时使用策略默认标的池。区间超出数据范围（见上方平台信息）时要提醒用户。
3. 多策略组合调用 run_portfolio_backtest，"等权"时不要传 weight；用户给了比例才传 weight。
4. 【不得编造】分析回测时只能使用工具返回的数据。引用的每个数字都必须与工具结果完全一致（直接照抄工具给出的字符串，如 "12.3%"），不得估算、推测或"假设"任何回测数字。工具里没有的数据就说没有，需要时调用 get_backtest_detail 查看。
5. 【优化建议】给出 1~3 条具体、可直接执行的建议，每条都包含四部分：
   - 问题：指出要解决的问题及数据证据（如最大回撤、某类行情的平均月收益、最长连续亏损、短线交易占比、成本拖累）；
   - 调整：写明参数名和具体数值，如"单品种仓位上限 position_limit 0.15 → 0.10""入场通道 entry_window 20 → 30"，也可以是"开启止损 stop_loss = 0.08"这类规则调整；
   - 预期方向：说明预计改善什么、代价是什么（如回撤下降但收益也可能下降），只说方向，不编造具体数值；
   - 原理：解释为什么这个调整会带来这种变化（如"海龟依靠突破开仓，震荡市的假突破带来连续亏损，降低单笔仓位能控制每次亏损的规模"）。
   不要只说"可以做参数敏感性分析"这类空泛建议。如果用户要求验证，或者你想展示效果，用 compare_params 实际跑出对比，不能凭空断言"调整后回撤会降到 X%"。同时提醒过拟合风险。
6. 【组合分析】用相关系数、分散化比率、风险贡献、组合与子策略回撤的对比来评价分散化效果，并分析子策略在不同行情下如何互补。
7. 【教学问答】原理、指标、概念类问题，先用 search_knowledge 检索平台知识库，以知识库为准回答，可以结合通用知识补充。讲解要通俗，适当举例。
8. 【合规】平台只用于教学，你不能给出任何实盘投资建议：不推荐买卖具体股票或合约，不预测价格走势，不给出实际仓位操作建议。遇到这类问题，礼貌说明原因，并引导用户用历史回测学习相关策略。回测结论只描述"策略在历史数据上的表现"。
9. 系统会在执行过回测的回复末尾自动附加免责声明，你不需要再写免责声明。

# 回复格式
- 使用中文和 Markdown，结构清晰、简洁，适合学生阅读；表格用于对比多组数字。
- 执行回测后的回复建议按以下结构：
  **【智能体响应】** 调取的策略、参数修改（原 → 新）、回测标的与区间
  **【量化指标】** 总收益率、年化收益率、最大回撤、夏普比率、卡玛比率、波动率、胜率、盈亏比、交易次数
  **【基准对比】** 与沪深 300 等基准的对比
  **【智能分析】** 表现评价：优势、缺陷、识别出的问题（附数据证据）
  **【优化建议】** 可落地的参数调整 + 原理说明
- 界面会自动显示净值曲线、回撤曲线、年度收益、交易点位等图表，文字中说明"图表已生成"即可，不要用文字画图。
- 用户想要原始数据（每日净值、交易记录、持仓明细）时，告诉他点击报告右上角的「导出数据」下载 CSV 数据集；在报告中点击净值曲线上的某一天可以查看当天持仓。"""


# ---------------------------------------------------------------- 事实核验

_NUM = re.compile(r"(?<![\w.])[-−+]?\d+(?:\.\d+)?(?=\s*%)|(?<![\w.%-])[-−+]?\d+\.\d+(?![\d%])")


def _numbers_in(text: str) -> list[tuple[str, float, int]]:
    out = []
    for m in _NUM.finditer(text):
        s = m.group(0).replace("−", "-")
        dec = len(s.split(".")[1]) if "." in s else 0
        try:
            out.append((m.group(0), float(s), dec))
        except ValueError:
            continue
    return out


def _collect_numbers(obj: Any, acc: dict[float, str], path: str = "") -> None:
    """收集数据来源中出现的所有数字，记录每个数字第一次出现的位置（来源 · 字段），供核验明细展示。"""
    def add(v: float, where: str) -> None:
        acc.setdefault(round(abs(v), 10), where)

    if isinstance(obj, dict):
        if "_src" in obj and "data" in obj:  # 带来源标签的工具结果
            _collect_numbers(obj["data"], acc, obj["_src"])
            return
        for k, v in obj.items():
            _collect_numbers(v, acc, f"{path} · {k}" if path else str(k))
    elif isinstance(obj, list):
        for v in obj:
            _collect_numbers(v, acc, path)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, int | float):
        add(float(obj), path)
        add(float(obj) * 100, path + "（×100）")
    elif isinstance(obj, str):
        snippet = obj if len(obj) <= 40 else ""
        for _raw, v, _ in _numbers_in(obj):
            add(v, f"{path}：{snippet}" if snippet else path)
        for x in re.findall(r"\d+(?:\.\d+)?", obj):
            add(float(x), f"{path}：{snippet}" if snippet else path)


def fact_check(answer: str, sources: list[Any]) -> dict[str, Any]:
    known: dict[float, str] = {}
    for s in sources:
        _collect_numbers(s, known)
    unmatched, matches = [], []
    checked = 0
    for raw, v, dec in _numbers_in(answer):
        checked += 1
        tol = 0.5 * 10 ** (-dec) + 1e-9
        hit = next((where for k, where in known.items() if abs(abs(v) - k) <= tol), None)
        if hit is None:
            unmatched.append(raw)
        elif len(matches) < 60:
            matches.append({"value": raw, "source": hit or "数据来源"})
    return {"checked": checked, "unmatched": list(dict.fromkeys(unmatched))[:10], "matches": matches,
            "status": "ok" if not unmatched else "warn"}


# ---------------------------------------------------------------- 会话

def get_or_create_session(session_id: str | None) -> ChatSession:
    import uuid

    from api import auth
    uid = auth.current_user_id()
    with Session(engine()) as s:
        if session_id:
            cs = s.get(ChatSession, session_id)
            if cs and (not auth.enabled() or cs.user_id == uid):
                return cs
            if cs:  # 别人的会话：另开一个新会话，不复用这个 id
                session_id = None
        cs = ChatSession(id=session_id or uuid.uuid4().hex[:12], user_id=uid)
        s.add(cs)
        s.commit()
        s.refresh(cs)
        return cs


def _history(session_id: str) -> list[dict]:
    with Session(engine()) as s:
        rows = list(s.exec(select(ChatMessage).where(ChatMessage.session_id == session_id)
                           .order_by(ChatMessage.id.desc()).limit(HISTORY_TURNS * 2)))
    rows.reverse()
    msgs: list[dict] = []
    for r in rows:
        if r.role == "user":
            msgs.append({"role": "user", "content": r.content})
        else:
            for m in json.loads(r.llm_json or "[]"):
                if m["role"] == "tool" and len(m.get("content", "")) > TOOL_RESULT_HISTORY_CHARS:
                    m = {**m, "content": m["content"][:TOOL_RESULT_HISTORY_CHARS] + "…（已截断）"}
                msgs.append(m)
            msgs.append({"role": "assistant", "content": r.content})
    # 截断后可能以孤立的工具消息开头，去掉
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def _title_from(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return t[:24] + ("…" if len(t) > 24 else "")


# ---------------------------------------------------------------- 一轮对话

# 等待学生确认的对话：session_id → {thread, message_id, user_text, payload}。
# 图的检查点也只在内存里，服务重启后待确认的步骤会失效，学生重新发送即可。
PENDING: dict[str, dict[str, Any]] = {}


async def run_turn(session_id: str | None, user_text: str, model: ModelRef | None = None, user: Any = None,
                   control: dict[str, Any] | None = None) -> AsyncIterator[dict[str, Any]]:
    import uuid

    ctl = Control.parse(control)
    cs = get_or_create_session(session_id)
    _expire_pending(cs.id)
    state = SessionState.load(cs.state_json)
    yield {"type": "session", "session_id": cs.id}

    sys = system_prompt(state) + ctl.prompt()
    messages: list[dict] = [{"role": "system", "content": sys}, *_history(cs.id)]
    if wants_investment_advice(user_text):
        messages.append({"role": "system", "content":
                         "注意：用户这条消息可能在寻求实盘投资建议。请明确说明本平台仅用于量化策略教学，"
                         "不提供任何买卖建议或行情预测，然后引导用户学习相关策略或做历史回测。"})
    messages.append({"role": "user", "content": user_text})
    # 核验来源：本轮与历史中的工具结果、用户输入、系统信息
    sources: list[Any] = [{"_src": "你的输入", "data": user_text}, {"_src": "平台信息（系统提示）", "data": sys}] + \
        [{"_src": "历史对话", "data": m["content"]} for m in messages if m["role"] in ("tool", "user")]
    init = {"mode": ctl.mode, "control": ctl.dump(), "session_id": cs.id, "session_state": cs.state_json or "",
            "messages": messages, "turn_msgs": [], "events": [], "sources": sources, "pending": [],
            "backtests": 0, "rounds": 0, "ran_backtest": False, "final": "", "model_used": None}
    thread = f"{cs.id}:{uuid.uuid4().hex[:8]}"
    async for ev in _drive(init, thread, cs.id, user_text, None, model, user):
        yield ev


async def resume_turn(session_id: str, decision: dict[str, Any], model: ModelRef | None = None,
                      user: Any = None) -> AsyncIterator[dict[str, Any]]:
    """学生确认（工具调用或计划）后，从暂停处继续执行。"""
    cs = get_or_create_session(session_id)
    p = PENDING.get(cs.id) if cs.id == session_id else None
    yield {"type": "session", "session_id": cs.id}
    if not p:
        yield {"type": "error", "message": "这一步的确认已经失效（可能服务重启过，或你已发送了新消息），请重新发送你的问题。"}
        yield {"type": "done", "message_id": None, "content": ""}
        return
    async for ev in _drive(Command(resume=decision), p["thread"], cs.id, p["user_text"], p["message_id"], model, user):
        yield ev


def pending_info(session_id: str) -> dict[str, Any] | None:
    p = PENDING.get(session_id)
    return {"message_id": p["message_id"], **p["payload"]} if p else None


async def _drive(inp: Any, thread: str, sid: str, user_text: str, message_id: int | None,
                 model: ModelRef | None, user: Any) -> AsyncIterator[dict[str, Any]]:
    config = {"configurable": {"thread_id": thread, "llm": stream_chat, "model": model, "user": user},
              "recursion_limit": 100}
    error = None
    try:
        async for mode, chunk in GRAPH.astream(inp, config, stream_mode=["custom", "updates"]):
            if mode == "custom":
                yield chunk
    except LLMError as e:
        error = f"抱歉，模型调用失败：{e}"
        yield {"type": "error", "message": str(e)}
    except Exception as e:
        error = f"抱歉，处理时出现错误：{type(e).__name__}"
        yield {"type": "error", "message": f"{type(e).__name__}: {e}"}

    snap = await GRAPH.aget_state(config)
    vals = snap.values
    events = list(vals.get("events", []))
    if snap.interrupts and not error:  # 暂停，等学生确认
        payload = plain(snap.interrupts[0].value)
        partial = vals.get("pending_text", "")
        mid = _save(sid, user_text, message_id, partial, events + [{**payload, "kind": "approval", "type": payload.get("kind"), "status": "pending"}],
                    vals, None)
        PENDING[sid] = {"thread": thread, "message_id": mid, "user_text": user_text, "payload": payload}
        yield {"type": "approval", "message_id": mid, **payload}
        yield {"type": "done", "message_id": mid, "content": partial, "paused": True}
        return

    PENDING.pop(sid, None)
    final = error or vals.get("final") or ""
    check = fact_check(final, vals.get("sources", [])) if final and not error else \
        {"status": "ok", "checked": 0, "unmatched": []}
    events.append({"kind": "fact_check", **check})
    yield {"type": "fact_check", **check}
    if vals.get("ran_backtest"):
        yield {"type": "disclaimer", "text": services.DISCLAIMER}
        final = f"{final.rstrip()}\n\n{services.DISCLAIMER}"
    mid = _save(sid, user_text, message_id, final, events, vals, vals.get("model_used"))
    yield {"type": "done", "message_id": mid, "content": final}


def _save(sid: str, user_text: str, message_id: int | None, content: str, events: list[dict],
          vals: dict[str, Any], model_used: str | None) -> int:
    """写入（或更新暂停时已写入的）本轮消息，并保存会话状态。"""
    events_json = json.dumps(events, ensure_ascii=False, default=str)
    llm_json = json.dumps(vals.get("turn_msgs", []), ensure_ascii=False, default=str)
    with Session(engine()) as s:
        msg = s.get(ChatMessage, message_id) if message_id else None
        if msg is None:
            s.add(ChatMessage(session_id=sid, role="user", content=user_text))
            msg = ChatMessage(session_id=sid, role="assistant", content="")
        msg.content, msg.events_json, msg.llm_json = content, events_json, llm_json
        msg.model = model_used or msg.model
        s.add(msg)
        row = s.get(ChatSession, sid)
        if vals.get("session_state"):
            row.state_json = vals["session_state"]
        row.updated_at = now()
        if row.title == "新对话":
            row.title = _title_from(user_text)
        s.add(row)
        s.commit()
        s.refresh(msg)
        return msg.id


def _expire_pending(sid: str) -> None:
    """学生没确认就发了新消息：上一轮暂停的步骤作废。"""
    p = PENDING.pop(sid, None)
    if not p:
        return
    with Session(engine()) as s:
        msg = s.get(ChatMessage, p["message_id"])
        if msg:
            events = json.loads(msg.events_json or "[]")
            for e in events:
                if e.get("kind") == "approval" and e.get("status") == "pending":
                    e["status"] = "expired"
            msg.events_json = json.dumps(events, ensure_ascii=False)
            s.add(msg)
            s.commit()
