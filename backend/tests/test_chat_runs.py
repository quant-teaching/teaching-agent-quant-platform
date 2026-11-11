"""对话生成与浏览器连接解耦：中途离开页面不丢对话，回来能接着看，也能停止。大模型用假模型代替。"""

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from agent import agent as agent_mod
from agent.llm import Completion
from api.main import app

ANSWER = "双均线策略在震荡市里容易反复止损，这是它的主要弱点。"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def slow_model(text=ANSWER, delay=0.03):
    async def fake_stream(messages, tools=None, prefer=None, user=None):
        yield {"type": "model", "provider": "假接口", "model": "fake", "fallback": False}
        for ch in text:
            await asyncio.sleep(delay)
            yield {"type": "delta", "text": ch}
        yield {"type": "done", "completion": Completion(content=text, tool_calls=[], model="fake", provider="假接口")}
    return fake_stream


def start_and_leave(client, message):
    """发出问题，收到第一段回答后就断开（相当于切换到其他页面），返回会话 id。"""
    sid = None
    with client.stream("POST", "/api/chat", json={"message": message}) as r:
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            ev = json.loads(line[5:])
            if ev["type"] == "session":
                sid = ev["session_id"]
            if ev["type"] == "delta":
                break
    return sid


def wait_finished(client, sid, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        s = client.get(f"/api/chat/sessions/{sid}").json()
        if not s["running"]:
            return s
        time.sleep(0.05)
    raise AssertionError("回答一直没有生成完")


def test_leaving_page_keeps_generating_and_saves(client, monkeypatch):
    monkeypatch.setattr(agent_mod, "stream_chat", slow_model())
    sid = start_and_leave(client, "双均线在震荡市表现如何")
    # 离开时问题已经保存，标题也已更新，回答还在生成
    s = client.get(f"/api/chat/sessions/{sid}").json()
    assert s["running"] is True
    assert s["messages"][0]["role"] == "user" and s["messages"][0]["content"] == "双均线在震荡市表现如何"
    assert s["title"].startswith("双均线")
    s = wait_finished(client, sid)
    assert [m["role"] for m in s["messages"]] == ["user", "assistant"]
    assert s["messages"][1]["content"] == ANSWER


def test_coming_back_replays_and_follows_live_answer(client, monkeypatch):
    monkeypatch.setattr(agent_mod, "stream_chat", slow_model())
    sid = start_and_leave(client, "讲讲双均线")
    events = []
    with client.stream("GET", f"/api/chat/sessions/{sid}/live") as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    assert events[0]["type"] == "session"
    assert "".join(e["text"] for e in events if e["type"] == "delta") == ANSWER  # 从头回放 + 继续接收
    assert events[-1]["type"] == "done"


def test_cannot_send_while_previous_answer_running(client, monkeypatch):
    monkeypatch.setattr(agent_mod, "stream_chat", slow_model())
    sid = start_and_leave(client, "第一个问题")
    r = client.post("/api/chat", json={"message": "第二个问题", "session_id": sid})
    assert r.status_code == 409
    wait_finished(client, sid)


def test_stop_saves_partial_answer(client, monkeypatch):
    monkeypatch.setattr(agent_mod, "stream_chat", slow_model(delay=0.2))
    sid = start_and_leave(client, "请详细解释")
    assert client.post(f"/api/chat/sessions/{sid}/stop").json()["stopped"] is True
    s = wait_finished(client, sid)
    content = s["messages"][1]["content"]
    assert content.endswith("（已停止生成）")
    assert content.startswith(ANSWER[0])


def test_live_for_idle_session_is_404(client, monkeypatch):
    monkeypatch.setattr(agent_mod, "stream_chat", slow_model(delay=0))
    sid = start_and_leave(client, "你好")
    wait_finished(client, sid)
    from api import chat_runs
    chat_runs.RUNS.pop(sid, None)  # 模拟保留期已过
    assert client.get(f"/api/chat/sessions/{sid}/live").status_code == 404
