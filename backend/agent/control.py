"""学生对智能体的控制设置：工作模式、允许使用的工具、可调用的策略范围、回测次数上限。

这些设置由学生在对话页的「智能体控制」面板中选择，随每次请求发送。它们不只是写进提示词，
而是在执行工具前由程序强制检查：模型即使"想"调用被禁用的工具或范围外的策略，也只会收到拒绝结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from api import services

from .tools import TOOL_LABELS, TOOLS

Mode = Literal["auto", "confirm", "plan", "research"]

MODE_LABELS: dict[str, str] = {
    "auto": "自动执行", "confirm": "每步确认", "plan": "先计划后执行", "research": "自主研究",
}
MODE_HINTS: dict[str, str] = {
    "auto": "",
    "confirm": "平台会在你每次调用工具之前自动暂停、请学生批准或修改，你不需要在文字里征求同意，"
               "按完成任务的需要直接发起工具调用即可；学生拒绝或修改后，以工具返回的结果和学生的意见为准继续。",
    "plan": "学生会先审核你的计划，再由程序按计划执行。",
    "research": "你要自主拆解目标、执行实验、根据结果反思并迭代，不需要征求学生同意。",
}
ALL_TOOLS = [t["function"]["name"] for t in TOOLS]
BACKTEST_COST = {"run_backtest": 1, "run_portfolio_backtest": 1}  # compare_params 按对比的参数值个数计


@dataclass
class Control:
    mode: Mode = "auto"
    tools: list[str] = field(default_factory=lambda: list(ALL_TOOLS))
    strategies: list[str] | None = None  # None 表示不限制
    max_backtests: int = 12
    max_iterations: int = 3  # 自主研究的最多迭代轮数

    @classmethod
    def parse(cls, raw: dict[str, Any] | None) -> Control:
        raw = raw or {}
        mode = raw.get("mode") if raw.get("mode") in MODE_LABELS else "auto"
        tools = raw.get("tools")
        tools = [t for t in ALL_TOOLS if t in tools] if isinstance(tools, list) else list(ALL_TOOLS)
        strategies = raw.get("strategies")
        if isinstance(strategies, list):
            ids = []
            for ref in strategies:
                try:
                    ids.append(services.get_entry(str(ref)).id)
                except services.NotFound:
                    continue
            strategies = list(dict.fromkeys(ids)) or None
        else:
            strategies = None
        clamp = lambda v, lo, hi, d: max(lo, min(hi, int(v))) if isinstance(v, int | float) else d  # noqa: E731
        return cls(mode=mode, tools=tools, strategies=strategies,
                   max_backtests=clamp(raw.get("max_backtests"), 1, 30, 12),
                   max_iterations=clamp(raw.get("max_iterations"), 1, 5, 3))

    def dump(self) -> dict[str, Any]:
        return {"mode": self.mode, "tools": self.tools, "strategies": self.strategies,
                "max_backtests": self.max_backtests, "max_iterations": self.max_iterations}

    # -- 给模型的工具与说明

    def tool_specs(self, exclude: set[str] | None = None) -> list[dict]:
        allowed = set(self.tools) - (exclude or set())
        return [t for t in TOOLS if t["function"]["name"] in allowed]

    def prompt(self) -> str:
        lines = ["\n# 学生的控制设置（必须遵守，程序也会强制检查）",
                 f"- 工作模式：{MODE_LABELS[self.mode]}。{MODE_HINTS[self.mode]}"]
        banned = [TOOL_LABELS.get(t, t) for t in ALL_TOOLS if t not in self.tools]
        if banned:
            lines.append(f"- 学生禁用了这些工具：{'、'.join(banned)}。不要尝试调用它们；需要时告诉学生可以在「智能体控制」中打开。")
        if self.strategies:
            names = []
            for sid in self.strategies:
                try:
                    names.append(f"{services.get_entry(sid).name}（{sid}）")
                except services.NotFound:
                    continue
            lines.append(f"- 学生只允许你使用这些策略：{'、'.join(names)}。不要调取或回测范围以外的策略。")
        lines.append(f"- 本轮对话最多执行 {self.max_backtests} 次回测（参数对比实验按对比的参数值个数计），用完后只能基于已有结果分析。")
        return "\n".join(lines)

    # -- 执行前检查

    def check(self, name: str, args: dict[str, Any], used_backtests: int) -> str | None:
        """返回拒绝原因；None 表示允许执行。"""
        if name not in self.tools:
            return f"学生在「智能体控制」中禁用了「{TOOL_LABELS.get(name, name)}」工具，不能调用。请基于已有信息回答，或提示学生打开该工具。"
        cost = backtest_cost(name, args)
        if cost and used_backtests + cost > self.max_backtests:
            return (f"本轮回测次数已达到学生设置的上限（{self.max_backtests} 次，已用 {used_backtests} 次），"
                    "不能再回测。请基于已有结果分析。")
        if self.strategies:
            for ref in strategy_refs(name, args):
                try:
                    entry = services.get_entry(ref)
                except services.NotFound:
                    continue  # 交给工具本身报"找不到策略"
                if entry.id not in self.strategies and entry.cls.id not in self.strategies:
                    return f"「{entry.name}」不在学生允许使用的策略范围内，不能调取或回测。允许的策略：{', '.join(self.strategies)}。"
        return None

    def filter_result(self, name: str, result: dict[str, Any], card: dict | None) -> tuple[dict, dict | None]:
        """策略范围受限时，算法库列表只返回范围内的策略。"""
        if name != "list_strategies" or not self.strategies:
            return result, card
        keep = [s for s in result.get("strategies", []) if s["id"] in self.strategies]
        result = {**result, "count": len(keep), "strategies": keep, "note": "已按学生设置的策略范围筛选"}
        if card:
            card = {**card, "items": keep}
        return result, card


def strategy_refs(name: str, args: dict[str, Any]) -> list[str]:
    refs = []
    for k in ("strategy", "base"):
        if isinstance(args.get(k), str) and args[k].strip():
            refs.append(args[k])
    if name == "run_portfolio_backtest":
        for c in args.get("components") or []:
            if isinstance(c, dict) and isinstance(c.get("strategy"), str):
                refs.append(c["strategy"])
    return refs


def backtest_cost(name: str, args: dict[str, Any]) -> int:
    if name == "compare_params":
        values = args.get("values")
        return len(values) if isinstance(values, list) else 1
    return BACKTEST_COST.get(name, 0)
