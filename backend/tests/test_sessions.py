"""对话列表的搜索和批量删除。大模型用假模型代替。"""

import json

import pytest
from fastapi.testclient import TestClient

from agent import agent as agent_mod
from agent.llm import Completion
from api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def answer_with(text):
    async def fake_stream(messages, tools=None, prefer=None, user=None):
        yield {"type": "model", "provider": "假接口", "model": "fake", "fallback": False}
        yield {"type": "delta", "text": text}
        yield {"type": "done", "completion": Completion(content=text, tool_calls=[], model="fake", provider="假接口")}
    return fake_stream


def chat(client, message):
    sid = None
    with client.stream("POST", "/api/chat", json={"message": message}) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                ev = json.loads(line[5:])
                if ev["type"] == "session":
                    sid = ev["session_id"]
    return sid


def test_search_matches_title_and_content(client, monkeypatch):
    monkeypatch.setattr(agent_mod, "stream_chat", answer_with("唐奇安通道由理查德·唐奇安提出，**突破上轨**时入场。"))
    a = chat(client, "讲讲搜索测试甲的原理")
    b = chat(client, "另一个问题")
    ids = {x["id"]: x for x in client.get("/api/chat/sessions", params={"q": "搜索测试甲"}).json()}
    assert a in ids and b not in ids  # 按标题命中
    hit = {x["id"]: x for x in client.get("/api/chat/sessions", params={"q": "突破上轨"}).json()}
    assert a in hit and b in hit  # 按回答内容命中
    assert "突破上轨" in hit[a]["snippet"] and "**" not in hit[a]["snippet"] and hit[a]["snippet_role"] == "assistant"
    # % 和 _ 按字面匹配，不当作通配符
    assert all(x["id"] not in (a, b) for x in client.get("/api/chat/sessions", params={"q": "%"}).json())


def test_batch_delete(client, monkeypatch):
    monkeypatch.setattr(agent_mod, "stream_chat", answer_with("好的"))
    a, b, c = chat(client, "批量一"), chat(client, "批量二"), chat(client, "批量三")
    r = client.post("/api/chat/sessions/batch-delete", json={"ids": [a, b, "不存在的id", a]}).json()
    assert r["deleted"] == 2
    left = {x["id"] for x in client.get("/api/chat/sessions").json()}
    assert a not in left and b not in left and c in left
    assert client.get(f"/api/chat/sessions/{a}").status_code == 404
