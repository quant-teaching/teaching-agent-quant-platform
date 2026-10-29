"""把自然语言里的策略称呼（"海龟""布林带股票""MACD 金叉死叉"）解析成算法库中的策略。"""

from __future__ import annotations

import re

from .base import Strategy, load_all

_FUT_HINT = ("期货", "商品", "cta", "主力合约", "做空")
_STOCK_HINT = ("股票", "a股", "选股", "个股", "沪深")


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-·（）()]+", "", s.lower())


def _names(cls: type[Strategy]) -> list[str]:
    return [cls.id, cls.name, *cls.aliases]


def match_strategies(text: str) -> list[tuple[type[Strategy], float]]:
    """返回按匹配度排序的候选。分数越高越确定。"""
    t = _norm(text)
    if not t:
        return []
    fut_hint = any(h in t for h in _FUT_HINT)
    stock_hint = any(h in t for h in _STOCK_HINT)
    scored = []
    for cls in load_all().values():
        best = 0.0
        for n in _names(cls):
            nn = _norm(n)
            if not nn:
                continue
            if t == nn:
                best = max(best, 100.0)
            elif nn in t:
                best = max(best, 50.0 + len(nn))  # 越长的名字越具体
            elif t in nn and len(t) >= 2:
                best = max(best, 30.0 + len(t))
        if best == 0:
            continue
        if fut_hint and cls.category == "futures":
            best += 8
        if stock_hint and cls.category == "stock":
            best += 8
        if fut_hint and not stock_hint and cls.category == "stock":
            best -= 8
        if stock_hint and not fut_hint and cls.category == "futures":
            best -= 8
        scored.append((cls, best))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def resolve_strategy(text: str) -> type[Strategy] | None:
    m = match_strategies(text)
    return m[0][0] if m else None
