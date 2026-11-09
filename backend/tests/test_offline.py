"""离线兜底：没有任何可用模型时，规则助手解析意图、调用工具、按模板整理真实结果。"""

import pytest
from fastapi.testclient import TestClient

from agent import llm as llm_mod
from agent.offline import parse_dates, plan_calls
from api.main import app
from api.settings import get_settings
from tests.test_agent_modes import chat

ALL = {"list_strategies", "get_strategy", "update_params", "run_backtest", "run_portfolio_backtest", "search_knowledge"}


@pytest.mark.parametrize("q, expect", [
    ("调出海龟交易期货策略，把 ATR 周期改为 22，单笔仓位上限 0.15，回测时间 2021-01-01 到 2024-12-30",
     [("update_params", {"strategy": "turtle_futures", "changes": {"atr_period": 22, "position_limit": 0.15}}),
      ("run_backtest", {"strategy": "turtle_futures", "start": "2021-01-01", "end": "2024-12-30"})]),
    ("选取双均线股票策略、动量选股策略，做等权组合，回测 2022-01-01 至 2025-06-30",
     [("run_portfolio_backtest", {"components": [{"strategy": "dual_ma_stock"}, {"strategy": "momentum_stock"}],
                                  "start": "2022-01-01", "end": "2025-06-30"})]),
    ("给我讲下布林带股票策略原理，它的可调参数是什么", [("get_strategy", {"strategy": "bollinger_stock"})]),
    ("什么是夏普比率", [("search_knowledge", {"query": "什么是夏普比率"})]),
    ("有哪些策略", [("list_strategies", {})]),
])
def test_rule_parsing(q, expect):
    assert plan_calls(q, ALL)[0] == expect


def test_disabled_tools_are_skipped():
    calls, note = plan_calls("用双均线回测 2023 年", ALL - {"run_backtest"})
    assert calls == [] and "禁用" in note


def test_dates():
    assert parse_dates("2021 到 2024") == ("2021-01-01", "2024-12-31")
    assert parse_dates("2023年1月5日至2023年6月30日") == ("2023-01-05", "2023-06-30")


def test_chat_works_without_any_model(monkeypatch):
    monkeypatch.setattr(llm_mod, "plan", lambda prefer, user=None: [])
    with TestClient(app) as c:
        ev = chat(c, "双均线策略短均线改成 5，回测 2023 年")
        assert [e for e in ev if e["type"] == "model"][-1]["model"] == "离线规则助手"
        ends = [e for e in ev if e["type"] == "tool_end"]
        assert [e["name"] for e in ends] == ["update_params", "run_backtest"] and all(e["ok"] for e in ends)
        fc = next(e for e in ev if e["type"] == "fact_check")
        assert fc["status"] == "ok" and fc["checked"] > 5  # 回复里的数字全部来自工具结果
        done = next(e for e in ev if e["type"] == "done")["content"]
        assert "离线模式" in done and "年化收益率" in done and "不构成任何投资建议" in done
        monkeypatch.setattr(get_settings(), "offline_fallback", False)
        err = [e for e in chat(c, "回测双均线") if e["type"] == "error"]
        assert err and "还没有配置可用的模型" in err[0]["message"]
