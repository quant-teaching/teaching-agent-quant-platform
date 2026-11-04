"""大模型接入：多接口管理、模型列表拉取、连接测试，以及主模型失败时自动切换备用模型。

所有接口都按 OpenAI 兼容协议调用（/models、/chat/completions），可以接 OpenAI、DeepSeek、
通义千问、各类中转站等。
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from api.db import LLMProvider, engine, get_setting, now, set_setting
from api.settings import get_settings

ROUTING_KEY = "llm.routing"


class ModelRef(BaseModel):
    provider_id: int
    model: str


class Routing(BaseModel):
    primary: ModelRef | None = None
    fallbacks: list[ModelRef] = Field(default_factory=list)
    temperature: float = Field(0.3, ge=0, le=2)
    timeout: float = Field(90, ge=5, le=600, description="单次请求超时（秒）")
    first_token_timeout: float = Field(45, ge=5, le=300, description="等待首个响应片段的超时（秒）")


class LLMError(RuntimeError):
    pass


# ---------------------------------------------------------------- 配置读写

def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def same_endpoint(a: str, b: str) -> bool:
    """两个 API 地址是否指向同一个服务（忽略末尾的 / 和 /v1、大小写）。"""
    def core(u: str) -> str:
        u = normalize_url(u).lower()
        return u.removesuffix("/v1").rstrip("/")
    return core(a) == core(b)


KEY_REQUIRED = "修改了 API 地址，请重新填写 API Key（已保存的 Key 不会发送到新地址）"


def mask_key(key: str) -> str:
    if not key:
        return ""
    return key[:5] + "••••" + key[-4:] if len(key) > 12 else "••••"


def provider_public(p: LLMProvider) -> dict[str, Any]:
    return {"id": p.id, "name": p.name, "base_url": p.base_url, "api_key_masked": mask_key(p.api_key),
            "has_key": bool(p.api_key), "models": p.models, "enabled": p.enabled,
            "updated_at": p.updated_at.isoformat()}


def list_providers() -> list[LLMProvider]:
    with Session(engine()) as s:
        return list(s.exec(select(LLMProvider).order_by(LLMProvider.id)))


def get_provider(pid: int) -> LLMProvider:
    with Session(engine()) as s:
        p = s.get(LLMProvider, pid)
        if not p:
            raise LLMError(f"模型接口 {pid} 不存在")
        return p


def upsert_provider(data: dict[str, Any], pid: int | None = None) -> LLMProvider:
    with Session(engine()) as s:
        p = s.get(LLMProvider, pid) if pid else LLMProvider(name="", base_url="")
        if pid and not p:
            raise LLMError(f"模型接口 {pid} 不存在")
        # 防止把已保存的 Key 带到别人的服务器：改了地址就必须同时重新填写 Key
        if pid and data.get("base_url") and not data.get("api_key") and not same_endpoint(data["base_url"], p.base_url):
            raise LLMError(KEY_REQUIRED)
        for k in ("name", "base_url", "enabled"):
            if data.get(k) is not None:
                setattr(p, k, normalize_url(data[k]) if k == "base_url" else data[k])
        if data.get("api_key"):  # 留空表示不修改
            p.api_key = data["api_key"].strip()
        if "models" in data and data["models"] is not None:
            p.models_json = json.dumps(sorted(set(data["models"])), ensure_ascii=False)
        p.updated_at = now()
        s.add(p)
        s.commit()
        s.refresh(p)
        return p


def delete_provider(pid: int) -> None:
    with Session(engine()) as s:
        p = s.get(LLMProvider, pid)
        if p:
            s.delete(p)
            s.commit()
    r = get_routing()
    if r.primary and r.primary.provider_id == pid:
        r.primary = None
    r.fallbacks = [f for f in r.fallbacks if f.provider_id != pid]
    save_routing(r)


def get_routing() -> Routing:
    return Routing(**get_setting(ROUTING_KEY, {}))


def save_routing(r: Routing) -> Routing:
    set_setting(ROUTING_KEY, r.model_dump())
    return r


def seed_from_env() -> None:
    """首次启动时，把环境文件里的接口写入数据库，作为默认配置。"""
    if list_providers():
        return
    s = get_settings()
    if not s.llm_base_url:
        return
    models = [m for m in (s.llm_model, s.llm_fallback_model) if m]
    p = upsert_provider({"name": s.llm_provider_name, "base_url": s.llm_base_url, "api_key": s.llm_api_key,
                         "models": models})
    r = Routing()
    if s.llm_model:
        r.primary = ModelRef(provider_id=p.id, model=s.llm_model)
    if s.llm_fallback_model:
        r.fallbacks = [ModelRef(provider_id=p.id, model=s.llm_fallback_model)]
    save_routing(r)


# ---------------------------------------------------------------- 模型列表与连接测试

async def fetch_models(base_url: str, api_key: str) -> tuple[str, list[str]]:
    """拉取模型列表。地址没写 /v1 时自动尝试补上，返回实际可用的地址。"""
    base = normalize_url(base_url)
    candidates = [base] if base.endswith("/v1") else [base, base + "/v1"]
    last_err = ""
    async with httpx.AsyncClient(timeout=20) as client:
        for b in candidates:
            try:
                resp = await client.get(f"{b}/models", headers={"Authorization": f"Bearer {api_key}"})
            except httpx.HTTPError as e:
                last_err = f"无法连接：{type(e).__name__}"
                continue
            if resp.status_code == 401:
                raise LLMError("API Key 无效或没有权限（401）")
            if resp.status_code >= 400:
                last_err = f"{resp.status_code} {resp.text[:120]}"
                continue
            try:
                data = resp.json()
            except ValueError:
                last_err = "返回的不是 JSON，可能地址不对"
                continue
            items = data.get("data", data if isinstance(data, list) else [])
            ids = sorted({m.get("id") for m in items if isinstance(m, dict) and m.get("id")})
            return b, ids
    raise LLMError(f"获取模型列表失败：{last_err}")


async def test_model(provider: LLMProvider, model: str, timeout: float = 30) -> dict[str, Any]:
    """发一条极短的请求，验证连通性、延迟和工具调用能力。"""
    client = AsyncOpenAI(base_url=provider.base_url, api_key=provider.api_key or "none", timeout=timeout,
                         max_retries=0)
    t0 = time.perf_counter()
    tool = {"type": "function", "function": {"name": "ping", "description": "连通性测试，必须调用",
                                             "parameters": {"type": "object", "properties": {}}}}
    try:
        resp = await client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": "请调用 ping 工具"}], tools=[tool], max_tokens=50,
        )
    except Exception as e:
        return {"ok": False, "error": _err_text(e), "latency_ms": int((time.perf_counter() - t0) * 1000)}
    msg = resp.choices[0].message if resp.choices else None
    return {"ok": True, "latency_ms": int((time.perf_counter() - t0) * 1000),
            "tool_calling": bool(msg and msg.tool_calls), "reply": (msg.content or "")[:80] if msg else ""}


def _err_text(e: Exception) -> str:
    status = getattr(e, "status_code", None)
    body = getattr(e, "body", None)
    detail = ""
    if isinstance(body, dict):
        detail = (body.get("error") or {}).get("message", "") if isinstance(body.get("error"), dict) else ""
    base = f"{type(e).__name__}" + (f"（{status}）" if status else "")
    return f"{base}：{detail or str(e)[:160]}"


# ---------------------------------------------------------------- 带故障切换的流式对话

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str = ""


@dataclass
class Completion:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    provider: str = ""


def candidates(routing: Routing | None = None) -> list[tuple[LLMProvider, str]]:
    r = routing or get_routing()
    providers = {p.id: p for p in list_providers() if p.enabled}
    out, seen = [], set()
    for ref in ([r.primary] if r.primary else []) + r.fallbacks:
        p = providers.get(ref.provider_id)
        if p and (p.id, ref.model) not in seen:
            seen.add((p.id, ref.model))
            out.append((p, ref.model))
    return out


def choices() -> dict[str, Any]:
    """对话页可选的模型：自动（主备顺序），以及每个启用接口下的模型（主备里用到的排在前面）。"""
    r = get_routing()
    refs = ([r.primary] if r.primary else []) + r.fallbacks
    chain = candidates(r)
    groups = []
    for p in list_providers():
        if not p.enabled:
            continue
        models = list(dict.fromkeys([x.model for x in refs if x.provider_id == p.id] + p.models))
        if models:
            groups.append({"provider_id": p.id, "provider": p.name, "models": models})
    return {"auto": {"primary": f"{chain[0][0].name} / {chain[0][1]}" if chain else None,
                     "fallbacks": max(len(chain) - 1, 0)},
            "groups": groups}


def _chain(routing: Routing, prefer: ModelRef | None) -> list[tuple[LLMProvider, str]]:
    """调用顺序：指定了模型就先用它，失败后再按主备顺序兜底；指定的必须是管理员配置过的模型。"""
    chain = candidates(routing)
    if prefer is None:
        return chain
    allowed = {(g["provider_id"], m) for g in choices()["groups"] for m in g["models"]}
    if (prefer.provider_id, prefer.model) not in allowed:
        raise LLMError("所选模型不可用（可能已被管理员停用或删除），请在对话页重新选择，或选「自动」")
    prov = get_provider(prefer.provider_id)
    return [(prov, prefer.model)] + [(p, m) for p, m in chain if (p.id, m) != (prov.id, prefer.model)]


async def stream_chat(messages: list[dict], tools: list[dict] | None = None,
                      prefer: ModelRef | None = None) -> AsyncIterator[dict]:
    """依次尝试指定模型（若有）、主模型和备用模型。产出事件：
    {"type": "model", ...} 开始使用某个模型；{"type": "delta", "text"} 文本片段；
    {"type": "switch", "from", "to", "reason"} 切换备用模型（前端应丢弃本轮已显示的片段）；
    {"type": "done", "completion": Completion}。
    """
    import asyncio

    routing = get_routing()
    chain = _chain(routing, prefer)
    if not chain:
        raise LLMError("还没有配置可用的模型，请先到「模型设置」添加接口并选择主模型")
    errors = []
    for i, (prov, model) in enumerate(chain):
        label = f"{prov.name} / {model}"
        if i > 0:
            yield {"type": "switch", "from": errors[-1][0], "to": label, "reason": errors[-1][1]}
        yield {"type": "model", "provider": prov.name, "model": model, "fallback": i > 0}
        client = AsyncOpenAI(base_url=prov.base_url, api_key=prov.api_key or "none", timeout=routing.timeout,
                             max_retries=0)
        comp = Completion(model=model, provider=prov.name)
        calls: dict[int, ToolCall] = {}
        try:
            kwargs: dict[str, Any] = {"model": model, "messages": messages, "stream": True,
                                      "temperature": routing.temperature}
            if tools:
                kwargs["tools"] = tools
            stream = await asyncio.wait_for(client.chat.completions.create(**kwargs),
                                            timeout=routing.first_token_timeout)
            it = stream.__aiter__()
            first = True
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        it.__anext__(), timeout=routing.first_token_timeout if first else routing.timeout)
                except StopAsyncIteration:
                    break
                first = False
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta is None:
                    continue
                if delta.content:
                    comp.content += delta.content
                    yield {"type": "delta", "text": delta.content}
                for tc in delta.tool_calls or []:
                    idx = tc.index if tc.index is not None else len(calls)
                    cur = calls.setdefault(idx, ToolCall(id=tc.id or f"call_{idx}", name=""))
                    if tc.id:
                        cur.id = tc.id
                    if tc.function and tc.function.name:
                        cur.name = tc.function.name
                    if tc.function and tc.function.arguments:
                        cur.arguments += tc.function.arguments
            comp.tool_calls = [c for _, c in sorted(calls.items()) if c.name]
            if not comp.content.strip() and not comp.tool_calls:
                raise LLMError("模型返回了空响应")
            yield {"type": "done", "completion": comp}
            return
        except Exception as e:  # 任何失败都切到下一个模型
            reason = "响应超时" if isinstance(e, asyncio.TimeoutError) else _err_text(e)
            errors.append((label, reason))
    detail = "；".join(f"{lb}：{r}" for lb, r in errors)
    raise LLMError(f"所有模型都调用失败（{detail}）")
