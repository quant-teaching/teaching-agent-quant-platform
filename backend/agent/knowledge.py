"""教学知识库检索（RAG）：策略教学文档 + 指标解释 + 回测概念，按小节切块，jieba 分词后用 BM25 检索。

当前接入的模型接口没有嵌入模型，而语料只有几十篇中文文档，关键词检索已经足够准确，
且结果可解释（能看到命中了哪些词），适合教学场景。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

from quant.strategies.base import load_all
from quant.strategies.resolve import match_strategies

jieba.setLogLevel(logging.WARNING)
KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

TERMS = [
    "最大回撤", "夏普比率", "卡玛比率", "索提诺比率", "年化收益率", "总收益率", "年化波动率", "盈亏比", "胜率",
    "利润因子", "信息比率", "换手率", "未来函数", "过拟合", "幸存者偏差", "前复权", "主力连续", "换月", "移仓",
    "保证金", "涨跌停", "均值回归", "趋势跟踪", "分散化", "相关系数", "风险平价", "动量效应", "反转效应",
    "金叉", "死叉", "布林带", "唐奇安通道", "真实波幅", "头寸单位", "金字塔加仓", "假突破", "震荡市", "单边行情",
    "股息率", "多因子", "截面标准化", "波动率目标", "跨期套利", "价差", "网格交易", "滑点", "印花税",
]
STOP = set("的 了 是 在 和 与 及 或 也 就 都 而 被 把 对 为 以 于 之 中 等 这 那 个 吗 呢 吧 啊 什么 怎么 如何 一个 我 你 它 给 讲 下 请 说 说明 一下".split())


@dataclass
class Chunk:
    source: str  # 文档标题
    section: str  # 小节标题
    text: str
    strategy_id: str | None = None


def _split(md: str, source: str, strategy_id: str | None) -> list[Chunk]:
    title_match = re.search(r"^# (.+)$", md, re.M)
    title = title_match.group(1).strip() if title_match else source
    parts = re.split(r"^## ", md, flags=re.M)
    head = parts[0]
    chunks = []
    intro = re.sub(r"^# .+$", "", head, flags=re.M).strip()
    if intro:
        chunks.append(Chunk(title, "概述", intro, strategy_id))
    for p in parts[1:]:
        sec, _, body = p.partition("\n")
        chunks.append(Chunk(title, sec.strip(), body.strip(), strategy_id))
    return chunks


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in jieba.lcut_for_search(text) if w.strip() and w not in STOP
            and not re.fullmatch(r"[\W_]+", w)]


@lru_cache(maxsize=1)
def _index() -> tuple[list[Chunk], BM25Okapi]:
    registry = load_all()
    for t in TERMS:
        jieba.add_word(t)
    for cls in registry.values():
        jieba.add_word(cls.name)
        for a in cls.aliases:
            jieba.add_word(a)
    chunks: list[Chunk] = []
    for cls in registry.values():
        doc = cls.doc()
        if doc:
            chunks.extend(_split(doc, cls.name, cls.id))
    for p in sorted(KNOWLEDGE_DIR.glob("*.md")):
        chunks.extend(_split(p.read_text(encoding="utf-8"), p.stem, None))
    # 标题和小节名重复一次，提高它们的权重
    cats = {cls.id: ("股票 股票策略" if cls.category == "stock" else "期货 期货策略 CTA") for cls in registry.values()}
    corpus = [tokenize(f"{cats.get(c.strategy_id, '')} {c.source} {c.source} {c.section} {c.section} {c.text}")
              for c in chunks]
    return chunks, BM25Okapi(corpus)


def search(query: str, k: int = 4, strategy_id: str | None = None) -> list[dict]:
    chunks, bm25 = _index()
    scores = bm25.get_scores(tokenize(query))
    # 问题里点名了某个策略时，提高该策略文档的权重
    named = match_strategies(query)
    if named and named[0][1] >= 50:
        target = named[0][0].id
        scores = [s * 1.6 if c.strategy_id == target else s for s, c in zip(scores, chunks)]
    ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    out = []
    for i in ranked:
        if scores[i] <= 0 or len(out) >= k:
            break
        c = chunks[i]
        if strategy_id and c.strategy_id not in (None, strategy_id):
            continue
        out.append({"source": c.source, "section": c.section, "text": c.text, "score": round(float(scores[i]), 2),
                    "strategy_id": c.strategy_id})
    return out


def strategy_sections(strategy_id: str) -> dict[str, str]:
    """某个策略文档的全部小节，供"讲讲这个策略"直接取用。"""
    chunks, _ = _index()
    return {c.section: c.text for c in chunks if c.strategy_id == strategy_id}
