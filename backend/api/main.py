"""FastAPI 入口。启动：在 backend/ 下运行 uv run uvicorn api.main:app --reload"""

from __future__ import annotations

import asyncio
import hmac
import json
from contextlib import asynccontextmanager
from typing import Any, Literal
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
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

from . import auth, instance, services
from .db import ChatMessage, ChatSession, engine
from .export import export_zip
from .serialize import clean
from .settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    instance.acquire()  # 同一个数据目录只允许一个实例，避免两个系统同时写数据库
    try:
        engine()
        llm.seed_from_env()
        auth.seed_admin()
        yield
    finally:
        services.shutdown_pool()
        instance.release()


PUBLIC_API = {"/api/health", "/api/auth/me", "/api/auth/login", "/api/auth/register", "/api/auth/logout"}


async def auth_guard(request: Request) -> None:
    """开启登录时，除登录相关接口外的 /api 都需要登录；当前用户放进上下文，供数据隔离使用。"""
    if not auth.enabled():
        return
    user = await run_in_threadpool(auth.user_from_request, request)
    auth.current_user.set(user)
    path = request.url.path
    if path.startswith("/api") and path not in PUBLIC_API and user is None:
        raise HTTPException(401, "请先登录")


app = FastAPI(title="面向教学的智能体驱动量化算法策略平台", version="0.1.0", lifespan=lifespan,
              dependencies=[Depends(auth_guard)])
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


@app.get("/api/backtests/{result_id}/export")
def backtest_export(result_id: str):
    name, data = export_zip(result_id)
    disposition = f"attachment; filename=\"backtest-{result_id}.zip\"; filename*=UTF-8''{quote(name)}"
    return Response(data, media_type="application/zip", headers={"Content-Disposition": disposition})


@app.delete("/api/backtests/{result_id}")
def remove_backtest(result_id: str):
    services.delete_record(result_id)
    return {"ok": True}


# ---------------------------------------------------------------- 账号

class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)
    remember: bool = False


class RegisterIn(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)
    invite_code: str = Field("", max_length=100)
    display_name: str = Field("", max_length=40)


class PasswordIn(BaseModel):
    old: str = Field(max_length=128)
    new: str = Field(max_length=128)


class UserPatch(BaseModel):
    disabled: bool


class InviteIn(BaseModel):
    code: str = Field("", max_length=40)
    enabled: bool = True


def require_role_admin() -> None:
    if not auth.is_admin():
        raise HTTPException(403, "只有管理员可以管理用户")


@app.get("/api/auth/me")
def auth_me(request: Request):
    st = get_settings()
    u = auth.user_from_request(request) if st.auth_enabled else None
    return {"enabled": st.auth_enabled, "user": auth.public(u) if u else None,
            "registration": bool(auth.active_invite_code()) if st.auth_enabled else False}


@app.post("/api/auth/login")
def auth_login(body: LoginIn, request: Request, response: Response):
    if not auth.enabled():
        raise HTTPException(400, "平台未开启登录")
    u = auth.login(body.username, body.password)
    auth.start_session(response, request, u, body.remember)
    return {"user": auth.public(u)}


@app.post("/api/auth/register")
def auth_register(body: RegisterIn, request: Request, response: Response):
    if not auth.enabled():
        raise HTTPException(400, "平台未开启登录")
    u = auth.register(body.username, body.password, body.invite_code, body.display_name)
    auth.start_session(response, request, u, remember=True)
    return {"user": auth.public(u)}


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    auth.end_session(request, response)
    return {"ok": True}


@app.post("/api/auth/password")
def auth_password(body: PasswordIn):
    u = auth.current_user.get()
    if not u:
        raise HTTPException(400, "平台未开启登录")
    auth.change_password(u, body.old, body.new)
    return {"ok": True}


@app.get("/api/auth/invite", dependencies=[Depends(require_role_admin)])
def get_invite():
    return auth.invite_config()


@app.put("/api/auth/invite", dependencies=[Depends(require_role_admin)])
def put_invite(body: InviteIn):
    return auth.set_invite(body.code, body.enabled)


@app.get("/api/auth/users", dependencies=[Depends(require_role_admin)])
def auth_users():
    return auth.list_users()


@app.patch("/api/auth/users/{uid}", dependencies=[Depends(require_role_admin)])
def auth_user_patch(uid: int, body: UserPatch):
    return auth.set_disabled(uid, body.disabled)


@app.delete("/api/auth/users/{uid}", dependencies=[Depends(require_role_admin)])
def auth_user_delete(uid: int):
    auth.delete_user(uid)
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


def require_admin(x_admin_password: str = Header("")) -> None:
    if auth.enabled():
        if not auth.is_admin():
            raise HTTPException(403, "只有管理员可以修改模型设置")
        return
    pw = get_settings().admin_password
    if pw and not hmac.compare_digest(x_admin_password.encode(), pw.encode()):
        raise HTTPException(403, "模型设置已锁定，请先在「模型设置」页面输入管理员密码解锁")


admin = [Depends(require_admin)]


class UnlockIn(BaseModel):
    password: str = Field(max_length=200)


@app.get("/api/llm/lock")
def lock_state():
    if auth.enabled():
        return {"locked": not auth.is_admin(), "mode": "role"}
    return {"locked": bool(get_settings().admin_password), "mode": "password"}


@app.post("/api/llm/unlock")
async def unlock(body: UnlockIn):
    pw = get_settings().admin_password
    if pw and not hmac.compare_digest(body.password.encode(), pw.encode()):
        await asyncio.sleep(1)  # 拖慢暴力猜测
        raise HTTPException(403, "管理员密码不正确")
    return {"ok": True}


@app.get("/api/llm/providers")
def providers():
    rows = [llm.provider_public(p) for p in llm.list_providers()]
    if auth.enabled() and not auth.is_admin():  # 普通用户连打码后的 Key 片段也不显示
        for r in rows:
            r["api_key_masked"] = "已设置" if r["has_key"] else ""
    return rows


@app.post("/api/llm/providers", dependencies=admin)
def add_provider(body: ProviderIn):
    if not body.name or not body.base_url:
        raise HTTPException(400, "名称和 API 地址不能为空")
    return llm.provider_public(llm.upsert_provider(body.model_dump()))


@app.put("/api/llm/providers/{pid}", dependencies=admin)
def edit_provider(pid: int, body: ProviderIn):
    return llm.provider_public(llm.upsert_provider(body.model_dump(), pid))


@app.delete("/api/llm/providers/{pid}", dependencies=admin)
def remove_provider(pid: int):
    llm.delete_provider(pid)
    return {"ok": True}


@app.post("/api/llm/models/fetch", dependencies=admin)
async def fetch_models(body: FetchModelsIn):
    key = body.api_key
    if not key and body.provider_id:
        p = llm.get_provider(body.provider_id)
        if not llm.same_endpoint(body.base_url, p.base_url):  # 已保存的 Key 只发给原来的地址
            raise HTTPException(400, llm.KEY_REQUIRED)
        key = p.api_key
    base, models = await llm.fetch_models(body.base_url, key or "")
    return {"base_url": base, "models": models}


@app.post("/api/llm/providers/{pid}/refresh-models", dependencies=admin)
async def refresh_models(pid: int):
    p = llm.get_provider(pid)
    base, models = await llm.fetch_models(p.base_url, p.api_key)
    p = llm.upsert_provider({"base_url": base, "models": models}, pid)
    return llm.provider_public(p)


@app.post("/api/llm/test", dependencies=admin)
async def test_model(body: TestIn):
    return await llm.test_model(llm.get_provider(body.provider_id), body.model)


@app.get("/api/llm/choices")
def llm_choices():
    """对话页的模型选择：自动（主备顺序）或指定某个接口的某个模型。不含地址和密钥，所有登录用户可见。"""
    return llm.choices()


@app.get("/api/llm/routing")
def routing():
    return llm.get_routing().model_dump()


@app.put("/api/llm/routing", dependencies=admin)
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
    model: llm.ModelRef | None = None  # 为空表示自动（按模型设置里的主备顺序）


@app.post("/api/chat")
async def chat(body: ChatIn):
    async def gen():
        async for ev in run_turn(body.session_id, body.message.strip(), body.model):
            yield {"data": json.dumps(clean(ev), ensure_ascii=False, default=str)}
    return EventSourceResponse(gen(), ping=15)


def _own_session(s: Session, sid: str) -> ChatSession:
    cs = s.get(ChatSession, sid)
    if not cs or (auth.enabled() and cs.user_id != auth.current_user_id()):
        raise services.NotFound("会话不存在")
    return cs


@app.get("/api/chat/sessions")
def chat_sessions():
    with Session(engine()) as s:
        q = select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(100)
        if auth.enabled():
            q = q.where(ChatSession.user_id == auth.current_user_id())
        rows = s.exec(q).all()
    return [{"id": r.id, "title": r.title, "updated_at": r.updated_at.isoformat()} for r in rows]


@app.get("/api/chat/sessions/{sid}")
def chat_session(sid: str):
    with Session(engine()) as s:
        cs = _own_session(s, sid)
        msgs = s.exec(select(ChatMessage).where(ChatMessage.session_id == sid).order_by(ChatMessage.id)).all()
    return {"id": cs.id, "title": cs.title, "state": json.loads(cs.state_json or "{}"),
            "messages": [{"id": m.id, "role": m.role, "content": m.content, "events": json.loads(m.events_json),
                          "model": m.model, "created_at": m.created_at.isoformat()} for m in msgs]}


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=60)


@app.patch("/api/chat/sessions/{sid}")
def rename_session(sid: str, body: RenameIn):
    with Session(engine()) as s:
        cs = _own_session(s, sid)
        cs.title = body.title
        s.add(cs)
        s.commit()
    return {"ok": True}


@app.delete("/api/chat/sessions/{sid}")
def delete_session(sid: str):
    with Session(engine()) as s:
        _own_session(s, sid)
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
