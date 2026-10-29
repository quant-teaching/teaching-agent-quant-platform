"""接口与智能体测试。大模型用脚本化的假模型代替，不访问网络。"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent import agent as agent_mod
from agent import llm as llm_mod
from agent.llm import Completion, ToolCall
from api.main import app

PERIOD = {"start": "2022-01-01", "end": "2024-12-31"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------- 算法库与回测

def test_health_market_strategies(client):
    assert client.get("/api/health").json() == {"ok": True}
    m = client.get("/api/market").json()
    assert len(m["stocks"]) == 55 and len(m["futures"]) == 16 and len(m["industries"]) == 31
    s = client.get("/api/strategies").json()
    assert len(s) == 22
    assert s[0]["id"] == "dual_ma_stock" and s[12]["id"] == "turtle_futures"  # 按赛题清单排序
    d = client.get("/api/strategies/海龟").json()  # 支持按名称或别名查找
    assert d["id"] == "turtle_futures" and "海龟" in d["doc"] and "class TurtleFutures" in d["source"]


def test_backtest_lifecycle(client):
    r = client.post("/api/backtests", json={"strategy": "布林带股票", "params": {"num_std": 2.5}, "config": PERIOD})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["params"]["num_std"] == 2.5
    assert len(p["series"]["dates"]) == len(p["series"]["nav"])
    assert set(p["series"]["benchmarks"]) == {"000300", "000905", "399006"}
    assert p["charts"] and p["trades"] and p["fills"]
    rid = p["id"]
    assert client.get(f"/api/backtests/{rid}").json()["id"] == rid
    assert any(x["id"] == rid for x in client.get("/api/backtests").json())
    hold = client.get(f"/api/backtests/{rid}/holdings", params={"date": "2023-06-30"}).json()
    assert all(h["date"] <= "2023-06-30" for h in hold)
    assert client.delete(f"/api/backtests/{rid}").json() == {"ok": True}
    assert client.get(f"/api/backtests/{rid}").status_code == 404


def test_backtest_errors_are_readable(client):
    r = client.post("/api/backtests", json={"strategy": "dual_ma_stock", "params": {"fast": 50, "slow": 20}, "config": PERIOD})
    assert r.status_code == 400 and "短均线周期必须小于长均线周期" in r.json()["detail"]
    r = client.post("/api/backtests", json={"strategy": "不存在的策略", "config": PERIOD})
    assert r.status_code == 404 and "你可能想找" in r.json()["detail"]
    r = client.post("/api/backtests", json={"strategy": "dual_ma_stock", "config": {"start": "2024-01-01", "end": "2023-01-01"}})
    assert r.status_code == 422


def test_portfolio_endpoint(client):
    r = client.post("/api/backtests/portfolio", json={
        "components": [{"strategy": "dual_ma_stock"}, {"strategy": "momentum_stock"}], "rebalance": "M", "config": PERIOD})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["kind"] == "portfolio" and len(p["components"]) == 2
    assert set(p["series"]["components"]) == {"双均线策略", "动量选股"}
    assert abs(sum(p["diagnostics"]["diversification"]["risk_contribution"]) - 1) < 1e-6
    for c in p["components"]:  # 子策略结果也已存档
        assert client.get(f"/api/backtests/{c['result_id']}").status_code == 200


def test_derived_strategy(client):
    r = client.post("/api/strategies/derived", json={"base": "turtle_futures", "name": "慢速海龟",
                                                     "params": {"entry_window": 55, "exit_window": 20}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["derived"] and d["base_id"] == "turtle_futures"
    assert next(p for p in d["params"] if p["key"] == "entry_window")["default"] == 55
    assert client.post("/api/strategies/derived", json={"base": "turtle_futures", "name": "慢速海龟"}).status_code == 400
    assert client.post("/api/strategies/derived", json={"base": "turtle_futures", "name": "海龟交易法则"}).status_code == 400
    p = client.post("/api/backtests", json={"strategy": "慢速海龟", "config": PERIOD}).json()
    assert p["params"]["entry_window"] == 55 and p["title"] == "慢速海龟"
    assert client.delete(f"/api/strategies/derived/{d['id']}").json() == {"ok": True}
    assert len(client.get("/api/strategies").json()) == 22


# ---------------------------------------------------------------- 模型设置

def test_provider_crud_and_routing(client):
    r = client.post("/api/llm/providers", json={"name": "测试接口", "base_url": "https://example.com/v1/",
                                                "api_key": "sk-1234567890abcdef", "models": ["m1", "m2"]})
    p = r.json()
    assert p["base_url"] == "https://example.com/v1"  # 去掉末尾斜杠
    assert "1234567890" not in json.dumps(p) and p["api_key_masked"].endswith("cdef")  # Key 不回传明文
    pid = p["id"]
    # 编辑时留空 Key 不会清掉原 Key
    client.put(f"/api/llm/providers/{pid}", json={"name": "改名", "api_key": ""})
    assert llm_mod.get_provider(pid).api_key == "sk-1234567890abcdef"
    body = {"primary": {"provider_id": pid, "model": "m1"}, "fallbacks": [{"provider_id": pid, "model": "m2"}],
            "temperature": 0.2, "timeout": 60, "first_token_timeout": 30}
    assert client.put("/api/llm/routing", json=body).json()["primary"]["model"] == "m1"
    bad = {**body, "fallbacks": [{"provider_id": 999, "model": "x"}]}
    assert client.put("/api/llm/routing", json=bad).status_code == 400
    # 删除接口时，引用它的主模型和备用模型一并移除
    client.delete(f"/api/llm/providers/{pid}")
    r = client.get("/api/llm/routing").json()
    assert r["primary"] is None and r["fallbacks"] == []


# ---------------------------------------------------------------- 智能体（假模型）

def scripted(turns):
    """按顺序返回预设的模型输出：每一轮是 (文本, [工具调用])。"""
    it = iter(turns)

    async def fake_stream(messages, tools=None):
        text, calls = next(it)
        yield {"type": "model", "provider": "假接口", "model": "fake", "fallback": False}
        for ch in text:
            yield {"type": "delta", "text": ch}
        yield {"type": "done", "completion": Completion(
            content=text, tool_calls=[ToolCall(id=f"c{i}", name=n, arguments=json.dumps(a, ensure_ascii=False))
                                      for i, (n, a) in enumerate(calls)], model="fake", provider="假接口")}
    return fake_stream


def chat(client, message, session_id=None):
    events = []
    with client.stream("POST", "/api/chat", json={"message": message, "session_id": session_id}) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return events


def test_agent_tool_loop_disclaimer_and_fact_check(client, monkeypatch):
    monkeypatch.setattr(agent_mod, "stream_chat", scripted([
        ("", [("get_strategy", {"strategy": "海龟"}),
              ("update_params", {"strategy": "turtle_futures", "changes": {"atr_period": 22}})]),
        ("", [("run_backtest", {"strategy": "turtle_futures", "start": "2021-01-01", "end": "2024-12-30"})]),
        ("回测完成，年化收益率 123.4%，夏普比率 9.99。", []),  # 故意编造的数字
    ]))
    ev = chat(client, "调出海龟策略，ATR 改成 22，回测 2021 到 2024")
    types = [e["type"] for e in ev]
    assert types[0] == "session" and types[-1] == "done"
    ends = [e for e in ev if e["type"] == "tool_end"]
    assert [e["name"] for e in ends] == ["get_strategy", "update_params", "run_backtest"] and all(e["ok"] for e in ends)
    diff = ends[1]["card"]["changes"][0]
    assert (diff["old"], diff["new"]) == (20, 22)
    assert ends[2]["card"]["kind"] == "backtest"
    fc = next(e for e in ev if e["type"] == "fact_check")
    assert fc["status"] == "warn" and set(fc["unmatched"]) == {"123.4", "9.99"}  # 编造的数字被识别
    assert "不构成任何投资建议" in ev[-1]["content"]  # 强制免责
    sid = ev[0]["session_id"]
    # 参数修改保存在会话中，下一轮回测自动使用
    monkeypatch.setattr(agent_mod, "stream_chat", scripted([
        ("", [("run_backtest", {"strategy": "turtle_futures", "start": "2022-01-01", "end": "2023-12-31"})]),
        ("好的。", []),
    ]))
    ev2 = chat(client, "换个区间再测一次", sid)
    rid = next(e for e in ev2 if e["type"] == "tool_end")["card"]["result_id"]
    assert client.get(f"/api/backtests/{rid}").json()["params"]["atr_period"] == 22
    hist = client.get(f"/api/chat/sessions/{sid}").json()
    assert [m["role"] for m in hist["messages"]] == ["user", "assistant", "user", "assistant"]


def test_agent_fact_check_passes_for_real_numbers(client, monkeypatch):
    captured = {}

    async def fake(messages, tools=None):
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        if not tool_msgs:
            yield {"type": "done", "completion": Completion(tool_calls=[ToolCall(
                id="c1", name="run_backtest",
                arguments=json.dumps({"strategy": "dual_ma_stock", "start": "2022-01-01", "end": "2024-12-31"}))])}
            return
        res = json.loads(tool_msgs[-1]["content"])
        text = f"年化收益率 {res['metrics']['年化收益率']}，最大回撤 {res['metrics']['最大回撤']}，夏普比率 {res['metrics']['夏普比率']}。"
        captured["text"] = text
        yield {"type": "done", "completion": Completion(content=text)}

    monkeypatch.setattr(agent_mod, "stream_chat", fake)
    ev = chat(client, "回测双均线")
    fc = next(e for e in ev if e["type"] == "fact_check")
    assert fc["status"] == "ok" and fc["checked"] == 3, captured


def test_agent_tool_error_is_fed_back(client, monkeypatch):
    seen = {}

    async def fake(messages, tools=None):
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        if not tool_msgs:
            yield {"type": "done", "completion": Completion(tool_calls=[ToolCall(
                id="c1", name="update_params", arguments=json.dumps({"strategy": "dual_ma_stock", "changes": {"fast": 99}}))])}
            return
        seen["err"] = json.loads(tool_msgs[-1]["content"]).get("error")
        yield {"type": "done", "completion": Completion(content="参数不合法，已说明。")}

    monkeypatch.setattr(agent_mod, "stream_chat", fake)
    ev = chat(client, "把双均线短周期改成 99")
    end = next(e for e in ev if e["type"] == "tool_end")
    assert not end["ok"] and "短均线周期必须小于长均线周期" in seen["err"]
    assert "不构成任何投资建议" not in ev[-1]["content"]  # 没有执行回测，不附加免责


def test_investment_advice_detection():
    for q in ("我该买哪只股票", "明天会涨吗", "推荐几只股票", "贵州茅台能不能买", "现在买还是卖"):
        assert agent_mod.wants_investment_advice(q), q
    for q in ("海龟交易法则原理是什么", "回测一下双均线策略", "夏普比率怎么算", "实盘和回测有什么区别"):
        assert not agent_mod.wants_investment_advice(q), q


def test_compliance_hint_injected(client, monkeypatch):
    got = {}

    async def fake(messages, tools=None):
        got["sys"] = [m["content"] for m in messages if m["role"] == "system"]
        yield {"type": "done", "completion": Completion(content="本平台仅用于教学。")}

    monkeypatch.setattr(agent_mod, "stream_chat", fake)
    chat(client, "我有10万块，该买哪只股票？")
    assert any("实盘投资建议" in s for s in got["sys"][1:])


# ---------------------------------------------------------------- 主备模型切换

class FakeOpenAI:
    """按模型名决定行为：bad 直接报错，empty 返回空内容，good 正常流式输出。"""

    def __init__(self, **kw):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, model, **kw):
        if model == "bad":
            raise RuntimeError("服务不可用")

        async def gen():
            if model == "good":
                for t in ("你", "好"):
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=t, tool_calls=None))])
        return gen()


@pytest.mark.anyio
async def test_fallback_chain(monkeypatch):
    p = llm_mod.upsert_provider({"name": "切换测试", "base_url": "https://x/v1", "api_key": "k", "models": ["bad", "empty", "good"]})
    llm_mod.save_routing(llm_mod.Routing(primary=llm_mod.ModelRef(provider_id=p.id, model="bad"),
                                         fallbacks=[llm_mod.ModelRef(provider_id=p.id, model="empty"),
                                                    llm_mod.ModelRef(provider_id=p.id, model="good")]))
    monkeypatch.setattr(llm_mod, "AsyncOpenAI", FakeOpenAI)
    events = [e async for e in llm_mod.stream_chat([{"role": "user", "content": "hi"}])]
    switches = [e for e in events if e["type"] == "switch"]
    assert [s["to"].split(" / ")[1] for s in switches] == ["empty", "good"]
    assert "服务不可用" in switches[0]["reason"] and "空响应" in switches[1]["reason"]
    done = events[-1]
    assert done["type"] == "done" and done["completion"].content == "你好" and done["completion"].model == "good"
    # 全部失败时给出汇总错误
    llm_mod.save_routing(llm_mod.Routing(primary=llm_mod.ModelRef(provider_id=p.id, model="bad")))
    with pytest.raises(llm_mod.LLMError, match="所有模型都调用失败"):
        _ = [e async for e in llm_mod.stream_chat([{"role": "user", "content": "hi"}])]
    llm_mod.delete_provider(p.id)


def test_result_id_path_traversal_rejected(client):
    for bad in ("..%2F..%2Fapp", "..", "abc.def"):
        assert client.get(f"/api/backtests/{bad}").status_code in (404, 405)
        assert client.get(f"/api/backtests/{bad}/holdings", params={"date": "2023-01-01"}).status_code in (404, 405)
        assert client.delete(f"/api/backtests/{bad}").status_code in (404, 405)


def test_report_served_gzip_directly(client):
    p = client.post("/api/backtests", json={"strategy": "dual_ma_stock", "config": PERIOD}).json()
    raw = client.get(f"/api/backtests/{p['id']}", headers={"Accept-Encoding": "gzip"})
    assert raw.headers["content-encoding"] == "gzip" and raw.json()["id"] == p["id"]
    plain = client.get(f"/api/backtests/{p['id']}", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers and plain.json()["metrics"] == p["metrics"]


def test_spa_route_blocks_path_traversal(client):
    from api import main
    if not main._dist.exists():
        pytest.skip("前端未构建")
    for p in ("/%2e%2e/%2e%2e/backend/api/settings.py", "/..%2F..%2Fbackend%2Fpyproject.toml",
              "/assets/..%2F..%2F..%2Fbackend%2Fpyproject.toml"):
        r = client.get(p)
        assert "pydantic" not in r.text and "BaseSettings" not in r.text, p
    assert client.get("/api/not-exist").status_code == 404
    assert "<div id=\"app\">" in client.get("/chat").text  # 前端路由仍然返回页面
