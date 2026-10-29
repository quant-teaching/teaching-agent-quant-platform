"""业务服务层：REST 接口和智能体工具共用同一套逻辑，保证两条路径结果一致。"""

from __future__ import annotations

import atexit
import gzip
import json
import multiprocessing
import uuid
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any

from sqlmodel import Session, select

from quant.backtest import BacktestResult, run_backtest
from quant.data.catalog import BENCHMARKS, FUTURES, STOCK_POOL
from quant.data.loader import data_range, industry_names
from quant.engine.config import BacktestConfig
from quant.portfolio.portfolio import Component, PortfolioSpec, run_portfolio
from quant.strategies.base import ParamError, Strategy, get_strategy_class, load_all
from quant.strategies.resolve import match_strategies

from .db import BacktestRecord, DerivedStrategy, engine
from .serialize import result_payload
from .settings import get_settings

DISCLAIMER = "⚠️ 本结果为教学回测模拟，历史回测不代表未来表现，不构成任何投资建议。"
SUMMARY_KEYS = ("total_return", "annual_return", "max_drawdown", "sharpe", "calmar", "volatility",
                "win_rate", "profit_loss_ratio", "trade_count")


class NotFound(LookupError):
    pass


# ---------------------------------------------------------------- 计算进程池

_pool: ProcessPoolExecutor | None = None


def compute(fn, *args, **kwargs):
    """在进程池中执行回测计算（CPU 密集，避免多人同时回测时互相排队），返回结果对象。

    每个工作进程各自缓存行情数据；保存结果、写数据库仍在主进程完成。
    """
    global _pool
    workers = get_settings().backtest_workers
    if workers <= 0:
        return fn(*args, **kwargs)
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))
        atexit.register(shutdown_pool)
    return _pool.submit(fn, *args, **kwargs).result()


def shutdown_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


@dataclass
class StrategyEntry:
    cls: type[Strategy]
    id: str
    name: str
    base_params: dict[str, Any]
    universe: str | None
    derived: DerivedStrategy | None = None

    def info(self) -> dict[str, Any]:
        d = self.cls.info()
        if self.derived:
            d.update(id=self.id, name=self.name, base_id=self.cls.id, base_name=self.cls.name, derived=True,
                     summary=self.derived.description or f"基于「{self.cls.name}」修改参数得到的衍生策略",
                     default_universe=self.universe or self.cls.default_universe)
            for p in d["params"]:
                if p["key"] in self.base_params:
                    p["default"] = self.base_params[p["key"]]
        else:
            d["derived"] = False
        return d


def _derived_all() -> list[DerivedStrategy]:
    with Session(engine()) as s:
        return list(s.exec(select(DerivedStrategy).order_by(DerivedStrategy.created_at)))


def _entry_from_derived(d: DerivedStrategy) -> StrategyEntry:
    return StrategyEntry(get_strategy_class(d.base_id), d.id, d.name, json.loads(d.params_json), d.universe, d)


def get_entry(ref: str) -> StrategyEntry:
    """按 id、名称、别名或自然语言描述查找策略（含衍生策略）。"""
    ref = (ref or "").strip()
    registry = load_all()
    if ref in registry:
        c = registry[ref]
        return StrategyEntry(c, c.id, c.name, {}, None)
    derived = _derived_all()
    for d in derived:
        if ref in (d.id, d.name):
            return _entry_from_derived(d)
    m = match_strategies(ref)
    if m and m[0][1] >= 40:
        c = m[0][0]
        return StrategyEntry(c, c.id, c.name, {}, None)
    for d in derived:
        if ref and (ref in d.name or d.name in ref):
            return _entry_from_derived(d)
    hint = "、".join(c.name for c, _ in m[:3]) if m else "、".join(c.name for c in list(registry.values())[:5])
    raise NotFound(f"算法库中没有找到「{ref}」，你可能想找：{hint}")


# 算法库展示顺序，与赛题给出的算法清单一致
ORDER = [
    "dual_ma_stock", "momentum_stock", "reversal_stock", "multi_factor_stock", "industry_rotation",
    "bollinger_stock", "rsi_stock", "grid_stock", "macd_stock", "kdj_stock", "risk_parity_stock",
    "dividend_rotation",
    "turtle_futures", "atr_channel_futures", "calendar_spread_futures", "trend_cta_futures",
    "mean_reversion_futures", "bollinger_futures", "volatility_breakout_futures", "ma_channel_futures",
    "grid_futures", "dual_ma_futures",
]


def catalog() -> list[dict[str, Any]]:
    rank = {sid: i for i, sid in enumerate(ORDER)}
    builtin = sorted(load_all().values(), key=lambda c: rank.get(c.id, len(ORDER)))
    out = [c.info() | {"derived": False} for c in builtin]
    out += [_entry_from_derived(d).info() for d in _derived_all()]
    return out


def save_derived(base_ref: str, name: str, params: dict[str, Any], description: str = "",
                 universe: str | None = None) -> dict[str, Any]:
    base = get_entry(base_ref)
    merged = {**base.base_params, **params}
    base.cls(merged)  # 校验参数
    name = name.strip()
    if not name:
        raise ParamError("衍生策略需要一个名称")
    if name in {c.name for c in load_all().values()}:
        raise ParamError(f"「{name}」与内置策略重名，请换一个名称")
    with Session(engine()) as s:
        if s.exec(select(DerivedStrategy).where(DerivedStrategy.name == name)).first():
            raise ParamError(f"已经存在名为「{name}」的衍生策略")
        d = DerivedStrategy(id="user_" + uuid.uuid4().hex[:8], base_id=base.cls.id, name=name,
                            description=description, params_json=json.dumps(merged, ensure_ascii=False),
                            universe=universe or base.universe)
        s.add(d)
        s.commit()
        s.refresh(d)
        return _entry_from_derived(d).info()


def delete_derived(strategy_id: str) -> None:
    with Session(engine()) as s:
        d = s.get(DerivedStrategy, strategy_id)
        if not d:
            raise NotFound("衍生策略不存在")
        s.delete(d)
        s.commit()


# ---------------------------------------------------------------- 回测

def _results_dir():
    p = get_settings().results_dir
    p.mkdir(parents=True, exist_ok=True)
    return p


def _universe_label(universe: list[dict[str, str]]) -> str:
    if len(universe) <= 3:
        return "、".join(u["name"] for u in universe)
    return f"{len(universe)} 个标的"


def persist_files(result: BacktestResult) -> dict[str, Any]:
    """生成报告 JSON 并写入存档文件。可以在工作进程中执行，返回给主进程的只有报告字典。"""
    import pandas as pd

    payload = result_payload(result)
    with gzip.open(_results_dir() / f"{result.id}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    if not result.positions.empty:
        result.positions.to_parquet(_results_dir() / f"{result.id}.positions.parquet", index=False)
    if result.fills:  # 报告 JSON 里的成交明细有条数上限，完整明细单独存档供导出
        pd.DataFrame([asdict(f) for f in result.fills]).to_parquet(
            _results_dir() / f"{result.id}.fills.parquet", index=False)
    return payload


def insert_record(payload: dict[str, Any], session_id: str | None, source: str) -> None:
    summary = {k: payload["metrics"].get(k) for k in SUMMARY_KEYS}
    hs = payload["benchmarks"].get("000300")
    if hs:
        summary["hs300_annual_return"] = hs["annual_return"]
    with Session(engine()) as s:
        s.add(BacktestRecord(
            id=payload["id"], kind=payload["kind"], title=payload["title"], strategy_id=payload["strategy"]["id"],
            category=payload["strategy"].get("category", ""), start=payload["config"]["start"],
            end=payload["config"]["end"], summary_json=json.dumps(summary, ensure_ascii=False),
            params_json=json.dumps(payload["params"], ensure_ascii=False),
            universe_label=_universe_label(payload["universe"]), session_id=session_id, source=source,
        ))
        s.commit()


def save_result(result: BacktestResult, session_id: str | None, source: str) -> dict[str, Any]:
    payload = persist_files(result)
    insert_record(payload, session_id, source)
    return payload


def _single_job(strategy_id: str, params: dict[str, Any], universe, config, title: str,
                derived: dict[str, str] | None) -> dict[str, Any]:
    """工作进程中执行：回测 → 生成报告 → 写存档文件。"""
    result = run_backtest(strategy_id, params, universe, config, title=title)
    if derived:
        result.strategy.update(derived)
    return persist_files(result)


def _portfolio_job(spec: PortfolioSpec, config) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result, subs = run_portfolio(spec, config)
    for comp, sub in zip(result.components, subs):
        comp["result_id"] = sub.id
    return persist_files(result), [persist_files(sub) for sub in subs]


def run_single(ref: str, params: dict[str, Any] | None, universe: str | list[str] | None,
               config: dict[str, Any] | BacktestConfig, *, session_id: str | None = None,
               source: str = "manual") -> dict[str, Any]:
    entry = get_entry(ref)
    merged = {**entry.base_params, **(params or {})}
    derived = {"derived_id": entry.id, "derived_name": entry.name} if entry.derived else None
    payload = compute(_single_job, entry.cls.id, merged, universe or entry.universe, config, entry.name, derived)
    insert_record(payload, session_id, source)
    return payload


def run_portfolio_service(components: list[dict[str, Any]], config: dict[str, Any] | BacktestConfig,
                          rebalance: str = "M", *, session_id: str | None = None,
                          source: str = "manual") -> dict[str, Any]:
    comps = []
    for c in components:
        entry = get_entry(c["strategy"])
        comps.append(Component(
            strategy_id=entry.cls.id, params={**entry.base_params, **(c.get("params") or {})},
            universe=c.get("universe") or entry.universe, weight=c.get("weight"), label=entry.name,
        ))
    payload, subs = compute(_portfolio_job, PortfolioSpec(components=comps, rebalance=rebalance), config)
    for sub in subs:  # 子策略也存档，方便单独查看
        insert_record(sub, session_id, source)
    insert_record(payload, session_id, source)
    return payload


def result_path(result_id: str):
    if not result_id.isalnum():
        raise NotFound(f"回测结果 {result_id} 不存在")
    return _results_dir() / f"{result_id}.json.gz"


@lru_cache(maxsize=8)  # 一份完整报告在内存中约十几 MB，只缓存最近几份
def load_payload(result_id: str) -> dict[str, Any]:
    path = result_path(result_id)
    if not path.exists():
        raise NotFound(f"回测结果 {result_id} 不存在")
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def holdings_on(result_id: str, date: str) -> list[dict[str, Any]]:
    import pandas as pd

    from quant.data.loader import symbol_name
    p = result_path(result_id).with_name(f"{result_id}.positions.parquet")
    if not p.exists():
        return []
    df = pd.read_parquet(p)
    d = df[df["date"] <= pd.Timestamp(date)]
    if d.empty:
        return []
    day = d[d["date"] == d["date"].max()]
    return [{"date": str(r.date.date()), "symbol": r.symbol, "name": symbol_name(r.symbol), "qty": r.qty,
             "price": r.price, "value": r.value, "weight": r.weight, "contract": r.contract}
            for r in day.itertuples()]


def list_records(limit: int = 50, session_id: str | None = None) -> list[dict[str, Any]]:
    with Session(engine()) as s:
        q = select(BacktestRecord).order_by(BacktestRecord.created_at.desc()).limit(limit)
        if session_id:
            q = q.where(BacktestRecord.session_id == session_id)
        rows = s.exec(q).all()
    return [{"id": r.id, "kind": r.kind, "title": r.title, "strategy_id": r.strategy_id, "category": r.category,
             "start": r.start, "end": r.end, "summary": json.loads(r.summary_json),
             "params": json.loads(r.params_json), "universe": r.universe_label, "source": r.source,
             "created_at": r.created_at.isoformat()} for r in rows]


def delete_record(result_id: str) -> None:
    result_path(result_id)  # 校验 id，防止路径穿越
    with Session(engine()) as s:
        r = s.get(BacktestRecord, result_id)
        if r:
            s.delete(r)
            s.commit()
    for suffix in (".json.gz", ".positions.parquet", ".fills.parquet"):
        (_results_dir() / f"{result_id}{suffix}").unlink(missing_ok=True)
    load_payload.cache_clear()


# ---------------------------------------------------------------- 数据概览

@lru_cache(maxsize=1)
def market_overview() -> dict[str, Any]:
    ranges = data_range()
    try:
        industries = [{"symbol": k, "name": v} for k, v in sorted(industry_names().items())]
    except Exception:
        industries = []
    return {
        "ranges": ranges,
        "stocks": [{"symbol": s.code, "name": s.name, "industry": s.industry} for s in STOCK_POOL],
        "futures": [{"symbol": f.code, "name": f.name, "exchange": f.exchange, "sector": f.sector,
                     "multiplier": f.multiplier, "margin_rate": f.margin_rate} for f in FUTURES],
        "industries": industries,
        "benchmarks": [{"code": b.code, "name": b.name} for b in BENCHMARKS],
        "universe_presets": [
            {"value": "stock_pool", "label": f"教学股票池（{len(STOCK_POOL)} 只沪深300龙头）"},
            {"value": "industries", "label": "申万一级行业指数（31 个）"},
            {"value": "futures", "label": f"商品期货主力合约（{len(FUTURES)} 个品种）"},
        ],
    }
