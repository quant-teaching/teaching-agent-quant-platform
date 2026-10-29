"""FastAPI 入口。启动：在 backend/ 下运行 uv run uvicorn api.main:app --reload"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from agent import knowledge, llm
from agent.agent import run_turn
from quant.data.loader import DataError
from quant.engine.config import BacktestConfig
from quant.paths import ROOT_DIR
from quant.strategies.base import ParamError

from . import services
from .db import ChatMessage, ChatSession, engine
from .serialize import clean
from .settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine()
    llm.seed_from_env()
    yield
    services.shutdown_pool()


app = FastAPI(title="面向教学的智能体驱动量化算法策略平台", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"],
                   allow_headers=["*"])
# 回测报告 JSON 较大（约 1 MB），压缩后约为原来的五分之一；SSE 流式响应默认不压缩
app.add_middleware(GZipMiddleware, minimum_size=2048)


@app.exception_handler(ParamError)
@app.exception_handler(DataError)
@app.exception_handler(llm.LLMError)
async def _bad_request(_: Request, e: Exception):
    return JSONResponse({"detail": str(e)}, status_code=400)


@app.exception_handler(services.NotFound)
async def _not_found(_: Request, e: Exception):
    return JSONResponse({"detail": str(e)}, status_code=404)


@app.exception_handler(ValidationError)
async def _validation(_: Request, e: ValidationError):
    msg = "；".join(str(err.get("ctx", {}).get("error", err["msg"])) for err in e.errors())
    return JSONResponse({"detail": msg}, status_code=400)


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- 数据与算法库

@app.get("/api/market")
def market():
    return services.market_overview()


@app.get("/api/strategies")
def strategies():
    return services.catalog()


@app.get("/api/strategies/{strategy_id}")
def strategy_detail(strategy_id: str):
    entry = services.get_entry(strategy_id)
    return {**entry.info(), "doc": entry.cls.doc(), "source": entry.cls.source(),
            "source_file": entry.cls.doc_path().with_suffix(".py").name}


class DerivedIn(BaseModel):
    base: str
    name: str
    params: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    universe: str | None = None


@app.post("/api/strategies/derived")
def create_derived(body: DerivedIn):
    return services.save_derived(body.base, body.name, body.params, body.description, body.universe)


@app.delete("/api/strategies/derived/{strategy_id}")
def remove_derived(strategy_id: str):
    services.delete_derived(strategy_id)
    return {"ok": True}


@app.get("/api/knowledge/search")
def knowledge_search(q: str, k: int = 5):
    return knowledge.search(q, k)


# ---------------------------------------------------------------- 回测

class BacktestIn(BaseModel):
    strategy: str
    params: dict[str, Any] = Field(default_factory=dict)
    universe: str | list[str] | None = None
    config: BacktestConfig


class PortfolioIn(BaseModel):
    components: list[dict[str, Any]] = Field(min_length=2, max_length=8)
    rebalance: Literal["none", "M", "Q"] = "M"
    config: BacktestConfig


@app.post("/api/backtests")
def create_backtest(body: BacktestIn):
    return services.run_single(body.strategy, body.params, body.universe, body.config, source="manual")


@app.post("/api/backtests/portfolio")
def create_portfolio(body: PortfolioIn):
    return services.run_portfolio_service(body.components, body.config, body.rebalance, source="manual")


@app.get("/api/backtests")
def backtests(limit: int = Query(50, le=500), session_id: str | None = None):
    return services.list_records(limit, session_id)


@app.get("/api/backtests/{result_id}")
def backtest(result_id: str, request: Request):
    # 存档本身就是 gzip 压缩的 JSON：浏览器支持 gzip 时原样返回，省去解压、解析和重新压缩
    path = services.result_path(result_id)
    if "gzip" in request.headers.get("accept-encoding", "") and path.exists():
        return Response(path.read_bytes(), media_type="application/json", headers={"Content-Encoding": "gzip"})
    return services.load_payload(result_id)


@app.get("/api/backtests/{result_id}/holdings")
def backtest_holdings(result_id: str, date: str):
    return services.holdings_on(result_id, date)


@app.delete("/api/backtests/{result_id}")
def remove_backtest(result_id: str):
    services.delete_record(result_id)
    return {"ok": True}


# ---------------------------------------------------------------- 模型设置

class ProviderIn(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None  # 编辑时留空表示不修改
    models: list[str] | None = None
    enabled: bool | None = None


class FetchModelsIn(BaseModel):
    base_url: str
    api_key: str | None = None
    provider_id: int | None = None  # 编辑已有接口且未重新填写 Key 时，用已保存的 Key


class TestIn(BaseModel):
    provider_id: int
    model: str


@app.get("/api/llm/providers")
def providers():
    return [llm.provider_public(p) for p in llm.list_providers()]


@app.post("/api/llm/providers")
def add_provider(body: ProviderIn):
    if not body.name or not body.base_url:
        raise HTTPException(400, "名称和 API 地址不能为空")
    return llm.provider_public(llm.upsert_provider(body.model_dump()))


@app.put("/api/llm/providers/{pid}")
def edit_provider(pid: int, body: ProviderIn):
    return llm.provider_public(llm.upsert_provider(body.model_dump(), pid))


@app.delete("/api/llm/providers/{pid}")
def remove_provider(pid: int):
    llm.delete_provider(pid)
    return {"ok": True}


@app.post("/api/llm/models/fetch")
async def fetch_models(body: FetchModelsIn):
    key = body.api_key
    if not key and body.provider_id:
        key = llm.get_provider(body.provider_id).api_key
    base, models = await llm.fetch_models(body.base_url, key or "")
    return {"base_url": base, "models": models}


@app.post("/api/llm/providers/{pid}/refresh-models")
async def refresh_models(pid: int):
    p = llm.get_provider(pid)
    base, models = await llm.fetch_models(p.base_url, p.api_key)
    p = llm.upsert_provider({"base_url": base, "models": models}, pid)
    return llm.provider_public(p)


@app.post("/api/llm/test")
async def test_model(body: TestIn):
    return await llm.test_model(llm.get_provider(body.provider_id), body.model)


@app.get("/api/llm/routing")
def routing():
    return llm.get_routing().model_dump()


@app.put("/api/llm/routing")
def save_routing(body: llm.Routing):
    ids = {p.id for p in llm.list_providers()}
    for ref in ([body.primary] if body.primary else []) + body.fallbacks:
        if ref.provider_id not in ids:
            raise HTTPException(400, f"模型接口 {ref.provider_id} 不存在")
    return llm.save_routing(body).model_dump()


# ---------------------------------------------------------------- 对话

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


@app.post("/api/chat")
async def chat(body: ChatIn):
    async def gen():
        async for ev in run_turn(body.session_id, body.message.strip()):
            yield {"data": json.dumps(clean(ev), ensure_ascii=False, default=str)}
    return EventSourceResponse(gen(), ping=15)


@app.get("/api/chat/sessions")
def chat_sessions():
    with Session(engine()) as s:
        rows = s.exec(select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(100)).all()
    return [{"id": r.id, "title": r.title, "updated_at": r.updated_at.isoformat()} for r in rows]


@app.get("/api/chat/sessions/{sid}")
def chat_session(sid: str):
    with Session(engine()) as s:
        cs = s.get(ChatSession, sid)
        if not cs:
            raise services.NotFound("会话不存在")
        msgs = s.exec(select(ChatMessage).where(ChatMessage.session_id == sid).order_by(ChatMessage.id)).all()
    return {"id": cs.id, "title": cs.title, "state": json.loads(cs.state_json or "{}"),
            "messages": [{"id": m.id, "role": m.role, "content": m.content, "events": json.loads(m.events_json),
                          "model": m.model, "created_at": m.created_at.isoformat()} for m in msgs]}


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=60)


@app.patch("/api/chat/sessions/{sid}")
def rename_session(sid: str, body: RenameIn):
    with Session(engine()) as s:
        cs = s.get(ChatSession, sid)
        if not cs:
            raise services.NotFound("会话不存在")
        cs.title = body.title
        s.add(cs)
        s.commit()
    return {"ok": True}


@app.delete("/api/chat/sessions/{sid}")
def delete_session(sid: str):
    with Session(engine()) as s:
        for m in s.exec(select(ChatMessage).where(ChatMessage.session_id == sid)).all():
            s.delete(m)
        cs = s.get(ChatSession, sid)
        if cs:
            s.delete(cs)
        s.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 前端静态文件（部署时）

_dist = ROOT_DIR / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    _dist_root = _dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/") or path == "api":
            raise HTTPException(404, "接口不存在")
        # 只允许返回前端构建目录内的文件，防止 ../ 路径穿越读取服务器上的其他文件（如密钥）
        f = (_dist_root / path).resolve()
        if path and f.is_file() and f.is_relative_to(_dist_root):
            return FileResponse(f)
        return FileResponse(_dist_root / "index.html")
