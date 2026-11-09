"""智能体工作模式与学生控制设置的测试（LangGraph 编排）。大模型用脚本化的假模型代替，不访问网络。"""

import json

import pytest
from fastapi.testclient import TestClient

from agent import agent as agent_mod
from agent.llm import Completion, ToolCall
from api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def scripted(turns, seen_tools=None):
    """按顺序返回预设的模型输出：每一轮是 (文本, [工具调用])。seen_tools 记录每次调用时提供给模型的工具名。"""
    it = iter(turns)

    async def fake_stream(messages, tools=None, prefer=None, user=None):
        if seen_tools is not None:
            seen_tools.append([t["function"]["name"] for t in tools or []])
        text, calls = next(it)
        yield {"type": "model", "provider": "假接口", "model": "fake", "fallback": False}
        for ch in text:
            yield {"type": "delta", "text": ch}
        yield {"type": "done", "completion": Completion(
            content=text, tool_calls=[ToolCall(id=f"c{i}", name=n, arguments=json.dumps(a, ensure_ascii=False))
                                      for i, (n, a) in enumerate(calls)], model="fake", provider="假接口")}
    return fake_stream


def _sse(client, url, body):
    events = []
    with client.stream("POST", url, json=body) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return events


def chat(client, message, control=None, session_id=None):
    return _sse(client, "/api/chat", {"message": message, "session_id": session_id, "control": control})


def resume(client, session_id, decision):
    return _sse(client, "/api/chat/resume", {"session_id": session_id, "decision": decision})


def kinds(events, t):
    return [e for e in events if e["type"] == t]


BT = {"strategy": "turtle_futures", "start": "2022-01-01", "end": "2023-12-31"}


def test_confirm_mode_pauses_and_applies_student_decisions(client, monkeypatch):
    monkeypatch.setattr(agent_mod, "stream_chat", scripted([
        ("我准备先改参数再回测。", [("update_params", {"strategy": "turtle_futures", "changes": {"atr_period": 30}}),
                         ("run_backtest", BT)]),
        ("好的，已按你的确认完成回测。", []),
    ]))
    ev = chat(client, "调出海龟改 ATR 回测", {"mode": "confirm"})
    sid = ev[0]["session_id"]
    ap = kinds(ev, "approval")[0]
    assert ap["kind"] == "tools" and [c["name"] for c in ap["calls"]] == ["update_params", "run_backtest"]
    assert not kinds(ev, "tool_end"), "确认之前不能执行任何工具"
    assert ev[-1]["type"] == "done" and ev[-1]["paused"]
    pending = client.get(f"/api/chat/sessions/{sid}").json()["pending"]
    assert pending["kind"] == "tools" and len(pending["calls"]) == 2

    # 学生拒绝改参数，并把回测结束日期改成 2023-06-30
    ids = {c["name"]: c["id"] for c in ap["calls"]}
    ev2 = resume(client, sid, {"calls": {ids["update_params"]: {"action": "reject"},
                                         ids["run_backtest"]: {"action": "approve", "args": {**BT, "end": "2023-06-30"}}},
                               "feedback": "先用默认参数看看"})
    ends = {e["name"]: e for e in kinds(ev2, "tool_end")}
    assert not ends["update_params"]["ok"] and "学生拒绝" in ends["update_params"]["error"]
    assert ends["run_backtest"]["ok"] and ends["run_backtest"]["card"]["period"] == "2022-01-01 ~ 2023-06-30"
    assert kinds(ev2, "disclaimer") and ev2[-1]["type"] == "done" and not ev2[-1].get("paused")
    s = client.get(f"/api/chat/sessions/{sid}").json()
    assert s["pending"] is None and len(s["messages"]) == 2  # 暂停前后是同一条回复
    approval = next(e for e in s["messages"][1]["events"] if e["kind"] == "approval")
    assert [i["action"] for i in approval["items"]] == ["rejected", "edited"]
    assert s["state"]["params"].get("turtle_futures", {}).get("atr_period") is None  # 被拒绝的修改没有生效


def test_new_message_expires_pending_confirmation(client, monkeypatch):
    monkeypatch.setattr(agent_mod, "stream_chat", scripted([
        ("", [("run_backtest", BT)]),
        ("直接回答。", []),
    ]))
    sid = chat(client, "回测海龟", {"mode": "confirm"})[0]["session_id"]
    chat(client, "算了，讲讲原理", {"mode": "auto"}, sid)
    s = client.get(f"/api/chat/sessions/{sid}").json()
    assert s["pending"] is None
    assert next(e for e in s["messages"][1]["events"] if e["kind"] == "approval")["status"] == "expired"
    ev = resume(client, sid, {"action": "approve"})
    assert kinds(ev, "error") and "失效" in kinds(ev, "error")[0]["message"]


PLAN = {"intro": "先了解策略，再回测，再看年度收益。", "steps": [
    {"tool": "get_strategy", "args": {"strategy": "dual_ma_stock"}, "why": "了解原理和参数"},
    {"tool": "run_backtest", "args": {"strategy": "dual_ma_stock", "start": "2022-01-01", "end": "2023-12-31"}, "why": "回测"},
    {"tool": "get_backtest_detail", "args": {"result_id": "$last", "section": "yearly"}, "why": "看分年表现"},
    {"tool": "not_a_tool", "args": {}, "why": "无效步骤应被丢弃"},
]}


def test_plan_mode_student_edits_plan_before_execution(client, monkeypatch):
    seen = []
    monkeypatch.setattr(agent_mod, "stream_chat", scripted([
        (json.dumps(PLAN, ensure_ascii=False), []),
        ("计划执行完毕，分析如下。", []),
    ], seen))
    ev = chat(client, "研究一下双均线", {"mode": "plan"})
    sid = ev[0]["session_id"]
    ap = kinds(ev, "approval")[0]
    assert ap["kind"] == "plan" and [s["tool"] for s in ap["steps"]] == ["get_strategy", "run_backtest", "get_backtest_detail"]
    assert not kinds(ev, "tool_end") and seen == [[]], "写计划时不给模型任何工具"

    steps = ap["steps"]
    steps[1]["args"]["end"] = "2022-12-31"  # 学生把回测区间改短
    ev2 = resume(client, sid, {"action": "approve", "steps": steps})
    ends = kinds(ev2, "tool_end")
    assert [e["name"] for e in ends] == ["get_strategy", "run_backtest", "get_backtest_detail"]
    assert all(e["ok"] for e in ends), ends
    assert ends[1]["card"]["period"] == "2022-01-01 ~ 2022-12-31"
    assert ev2[-1]["content"].startswith("计划执行完毕") and seen[-1] == []  # 总结时也不给工具


def test_plan_mode_cancel(client, monkeypatch):
    monkeypatch.setattr(agent_mod, "stream_chat", scripted([(json.dumps(PLAN, ensure_ascii=False), [])]))
    sid = chat(client, "研究一下双均线", {"mode": "plan"})[0]["session_id"]
    ev = resume(client, sid, {"action": "cancel"})
    assert not kinds(ev, "tool_end") and "已取消" in ev[-1]["content"]


def test_research_mode_iterates_with_reflection(client, monkeypatch):
    goal = {"goal": "找一个最大回撤更小的海龟参数", "criteria": "最大回撤小于原版", "steps": ["先回测原版"]}
    monkeypatch.setattr(agent_mod, "stream_chat", scripted([
        (json.dumps(goal, ensure_ascii=False), []),                       # 研究计划
        ("", [("run_backtest", BT)]),                                      # 第 1 轮执行
        ("第 1 轮：原版已回测。", []),                                        # 第 1 轮小结
        (json.dumps({"goal_met": False, "assessment": "还没有对比", "next": "降低仓位再测"}, ensure_ascii=False), []),
        ("", [("run_backtest", {**BT, "params": {"position_limit": 0.1}})]),  # 第 2 轮执行
        ("第 2 轮：低仓位已回测。", []),
        (json.dumps({"goal_met": True, "assessment": "回撤变小", "next": ""}, ensure_ascii=False), []),
        ("【研究目标】……【结论】低仓位版本回撤更小。", []),                     # 研究报告
    ]))
    ev = chat(client, "帮我找一个回撤更小的海龟参数", {"mode": "research", "max_iterations": 3})
    phases = [e["name"] for e in kinds(ev, "phase") if e["name"] not in ("planning", "reflecting")]
    assert phases == ["research_plan", "iteration", "reflect", "iteration", "reflect", "report"], phases
    assert len([e for e in kinds(ev, "tool_end") if e["ok"]]) == 2
    reflects = [e for e in kinds(ev, "phase") if e["name"] == "reflect"]
    assert [r["goal_met"] for r in reflects] == [False, True] and reflects[-1]["stop_reason"] == "目标已达成"
    assert "低仓位版本回撤更小" in ev[-1]["content"] and kinds(ev, "disclaimer")


def test_research_mode_stops_at_iteration_limit(client, monkeypatch):
    goal = {"goal": "g", "criteria": "c", "steps": ["s"]}
    monkeypatch.setattr(agent_mod, "stream_chat", scripted([
        (json.dumps(goal), []), ("第 1 轮小结。", []),
        (json.dumps({"goal_met": False, "assessment": "a", "next": "n"}), []),
        ("报告。", []),
    ]))
    ev = chat(client, "研究", {"mode": "research", "max_iterations": 1})
    reflect = next(e for e in kinds(ev, "phase") if e["name"] == "reflect")
    assert reflect["stop_reason"] == "已达到最多迭代轮数" and ev[-1]["content"] == "报告。"


def test_control_disabled_tool_and_strategy_scope_are_enforced(client, monkeypatch):
    seen = []
    tools = [t for t in agent_mod.Control.parse(None).tools if t != "run_backtest"]
    monkeypatch.setattr(agent_mod, "stream_chat", scripted([
        ("", [("run_backtest", BT), ("get_strategy", {"strategy": "海龟"}), ("list_strategies", {}),
              ("get_strategy", {"strategy": "双均线"})]),
        ("好的。", []),
    ], seen))
    ev = chat(client, "回测海龟", {"mode": "auto", "tools": tools, "strategies": ["dual_ma_stock", "momentum_stock"]})
    assert "run_backtest" not in seen[0], "禁用的工具不提供给模型"
    ends = kinds(ev, "tool_end")
    assert not ends[0]["ok"] and "禁用" in ends[0]["error"]
    assert not ends[1]["ok"] and "不在学生允许使用的策略范围" in ends[1]["error"]
    assert ends[2]["ok"] and [i["id"] for i in ends[2]["card"]["items"]] == ["dual_ma_stock", "momentum_stock"]
    assert ends[3]["ok"]


def test_control_backtest_budget(client, monkeypatch):
    seen = []
    monkeypatch.setattr(agent_mod, "stream_chat", scripted([
        ("", [("run_backtest", BT), ("run_backtest", {**BT, "end": "2023-06-30"})]),
        ("好的。", []),
    ], seen))
    ev = chat(client, "回测两次", {"max_backtests": 1})
    ends = kinds(ev, "tool_end")
    assert ends[0]["ok"] and not ends[1]["ok"] and "上限" in ends[1]["error"]
    assert "run_backtest" not in seen[1], "额度用完后不再向模型提供回测工具"


def test_control_parse_is_defensive():
    c = agent_mod.Control.parse({"mode": "hack", "tools": ["run_backtest", "rm_rf"], "strategies": ["海龟", "不存在"],
                                 "max_backtests": 999, "max_iterations": 0})
    assert c.mode == "auto" and c.tools == ["run_backtest"] and c.strategies == ["turtle_futures"]
    assert c.max_backtests == 30 and c.max_iterations == 1
