"""对话智能体：调度层。解析用户的自然语言 → 调用算法库、回测引擎、知识库工具 → 基于工具结果做教学分析。

三道保障：
1. 免责：本轮只要执行过回测，回复末尾由程序追加免责声明，不依赖模型自觉；
2. 合规：识别寻求实盘投资建议的提问，提示模型拒绝并引导回教学；
3. 防编造：回复中出现的百分数和小数必须能在工具结果、用户输入或系统信息中找到，否则标记为"未核验"。
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from sqlmodel import Session, select

from api import services
from api.db import ChatMessage, ChatSession, engine, now
from quant.data.catalog import FUTURES
from quant.strategies.base import load_all

from .llm import LLMError, stream_chat
from .tools import TOOL_LABELS, TOOLS, SessionState, Toolbox, ToolError, today

MAX_ROUNDS = 8
HISTORY_TURNS = 10
TOOL_RESULT_HISTORY_CHARS = 2500
BACKTEST_TOOLS = {"run_backtest", "run_portfolio_backtest", "compare_params"}

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
- 数据范围：A 股与申万行业 {rng('stock')}；商品期货主力连续合约 {rng('futures')}（由单合约按持仓量自建，2019 年下半年起可用）。
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
2. 用户要求回测时调用 run_backtest。用户没给时间区间时，使用 2022-01-01 至 2025-12-31 并告诉用户；没给标的时使用策略默认标的池。期货数据从 2019 年下半年开始，更早的区间要提醒用户。
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
- 界面会自动显示净值曲线、回撤曲线、年度收益、交易点位等图表，文字中说明"图表已生成"即可，不要用文字画图。"""


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


def _collect_numbers(obj: Any, acc: set[float]) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _collect_numbers(v, acc)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, int | float):
        acc.add(abs(float(obj)))
        acc.add(abs(float(obj)) * 100)
    elif isinstance(obj, str):
        for _, v, _ in _numbers_in(obj):
            acc.add(abs(v))
        for s in re.findall(r"\d+(?:\.\d+)?", obj):
            acc.add(abs(float(s)))


def fact_check(answer: str, sources: list[Any]) -> dict[str, Any]:
    known: set[float] = set()
    for s in sources:
        _collect_numbers(s, known)
    unmatched = []
    checked = 0
    for raw, v, dec in _numbers_in(answer):
        checked += 1
        tol = 0.5 * 10 ** (-dec) + 1e-9
        if not any(abs(abs(v) - k) <= tol for k in known):
            unmatched.append(raw)
    return {"checked": checked, "unmatched": list(dict.fromkeys(unmatched))[:10],
            "status": "ok" if not unmatched else "warn"}


# ---------------------------------------------------------------- 会话

def get_or_create_session(session_id: str | None) -> ChatSession:
    import uuid
    with Session(engine()) as s:
        if session_id:
            cs = s.get(ChatSession, session_id)
            if cs:
                return cs
        cs = ChatSession(id=session_id or uuid.uuid4().hex[:12])
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


def _tool_label(name: str, args: dict[str, Any]) -> str:
    base = TOOL_LABELS.get(name, name)
    target = args.get("strategy") or args.get("base") or args.get("query") or ""
    if name == "run_portfolio_backtest":
        target = " + ".join(c.get("strategy", "") for c in args.get("components", []))
    if args.get("start") and args.get("end"):
        target += f"（{args['start']} ~ {args['end']}）"
    return f"{base}：{target}" if target else base


async def run_turn(session_id: str | None, user_text: str) -> AsyncIterator[dict[str, Any]]:
    cs = get_or_create_session(session_id)
    state = SessionState.load(cs.state_json)
    toolbox = Toolbox(state, cs.id)
    yield {"type": "session", "session_id": cs.id}

    sys = system_prompt(state)
    messages: list[dict] = [{"role": "system", "content": sys}, *_history(cs.id)]
    if wants_investment_advice(user_text):
        messages.append({"role": "system", "content":
                         "注意：用户这条消息可能在寻求实盘投资建议。请明确说明本平台仅用于量化策略教学，"
                         "不提供任何买卖建议或行情预测，然后引导用户学习相关策略或做历史回测。"})
    messages.append({"role": "user", "content": user_text})

    turn_msgs: list[dict] = []  # 本轮新增、需要存档给后续上下文的消息
    events: list[dict] = []  # 前端卡片
    # 核验来源：本轮与历史中的工具结果、用户输入、系统信息
    sources: list[Any] = [user_text, sys] + [m["content"] for m in messages if m["role"] in ("tool", "user")]
    ran_backtest = False
    final = ""
    model_used = None

    try:
        for _ in range(MAX_ROUNDS):
            completion = None
            async for ev in stream_chat(messages + turn_msgs, TOOLS):
                if ev["type"] == "done":
                    completion = ev["completion"]
                    continue
                if ev["type"] == "model":
                    model_used = f"{ev['provider']} / {ev['model']}"
                if ev["type"] == "switch":
                    events.append({"kind": "model_switch", **{k: ev[k] for k in ("from", "to", "reason")}})
                yield ev
            assert completion is not None
            if not completion.tool_calls:
                final = completion.content
                break
            turn_msgs.append({
                "role": "assistant", "content": completion.content or "",
                "tool_calls": [{"id": c.id, "type": "function",
                                "function": {"name": c.name, "arguments": c.arguments or "{}"}}
                               for c in completion.tool_calls],
            })
            if completion.content:
                yield {"type": "round_text_end"}
            for call in completion.tool_calls:
                try:
                    args = json.loads(call.arguments or "{}")
                except json.JSONDecodeError:
                    args = None
                label = _tool_label(call.name, args or {})
                yield {"type": "tool_start", "id": call.id, "name": call.name, "label": label, "args": args}
                card = None
                if args is None:
                    result: dict[str, Any] = {"error": "参数不是合法的 JSON，请重新生成"}
                    ok = False
                else:
                    try:
                        result, card = await asyncio.to_thread(toolbox.call, call.name, args)
                        ok = True
                        if call.name in BACKTEST_TOOLS:
                            ran_backtest = True
                    except ToolError as e:
                        result, ok = {"error": str(e)}, False
                    except Exception as e:  # 工具内部异常也反馈给模型，让它调整
                        result, ok = {"error": f"{type(e).__name__}: {e}"}, False
                sources.append(result)
                content = json.dumps(result, ensure_ascii=False, default=str)
                turn_msgs.append({"role": "tool", "tool_call_id": call.id, "content": content})
                ev = {"type": "tool_end", "id": call.id, "name": call.name, "label": label, "ok": ok,
                      "error": None if ok else result.get("error"), "card": card}
                events.append({"kind": "tool", **{k: ev[k] for k in ("id", "name", "label", "ok", "error", "card")}})
                yield ev
        else:
            final = final or "（工具调用轮数过多，已停止。请把问题拆小一些再试。）"
    except LLMError as e:
        yield {"type": "error", "message": str(e)}
        final = f"抱歉，模型调用失败：{e}"
    except Exception as e:
        yield {"type": "error", "message": f"{type(e).__name__}: {e}"}
        final = f"抱歉，处理时出现错误：{type(e).__name__}"

    check = fact_check(final, sources) if final else {"status": "ok", "checked": 0, "unmatched": []}
    events.append({"kind": "fact_check", **check})
    yield {"type": "fact_check", **check}
    if ran_backtest:
        yield {"type": "disclaimer", "text": services.DISCLAIMER}
        final = f"{final.rstrip()}\n\n{services.DISCLAIMER}"

    with Session(engine()) as s:
        s.add(ChatMessage(session_id=cs.id, role="user", content=user_text))
        msg = ChatMessage(session_id=cs.id, role="assistant", content=final,
                          events_json=json.dumps(events, ensure_ascii=False, default=str),
                          llm_json=json.dumps(turn_msgs, ensure_ascii=False, default=str), model=model_used)
        s.add(msg)
        row = s.get(ChatSession, cs.id)
        row.state_json = state.dump()
        row.updated_at = now()
        if row.title == "新对话":
            row.title = _title_from(user_text)
        s.add(row)
        s.commit()
        s.refresh(msg)
        mid = msg.id
    yield {"type": "done", "message_id": mid, "content": final}
