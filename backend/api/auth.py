"""账号登录：用户名 + 密码，HttpOnly Cookie 会话；注册需要邀请码。

AUTH_ENABLED 关闭时（本地单人使用）不做任何校验，current_user 为空，所有数据不区分用户。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading
import time
from contextvars import ContextVar
from typing import Any

from fastapi import HTTPException, Request, Response
from sqlmodel import Session, select

from .db import AuthSession, User, engine, now
from .settings import get_settings

COOKIE = "qt_session"
SESSION_DAYS, REMEMBER_DAYS = 1, 30
MAX_FAILS, LOCK_SECONDS = 5, 300
USERNAME_RE = re.compile(r"^[A-Za-z0-9_一-龥]{2,20}$")

current_user: ContextVar[User | None] = ContextVar("current_user", default=None)


def enabled() -> bool:
    return get_settings().auth_enabled


def current_user_id() -> int | None:
    u = current_user.get()
    return u.id if u else None


def is_admin() -> bool:
    u = current_user.get()
    return bool(u and u.role == "admin")


def public(u: User) -> dict[str, Any]:
    return {"id": u.id, "username": u.username, "display_name": u.display_name or u.username, "role": u.role,
            "disabled": u.disabled, "created_at": u.created_at.isoformat(),
            "last_login": u.last_login.isoformat() if u.last_login else None}


# ---------------------------------------------------------------- 密码

def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(got, base64.b64decode(h))
    except ValueError:
        return False


def check_password_rule(pw: str) -> None:
    if len(pw) < 8 or len(pw) > 64:
        raise HTTPException(400, "密码长度需要在 8 到 64 位之间")
    if pw.isdigit() or pw.isalpha():
        raise HTTPException(400, "密码需要同时包含字母和数字")


# ---------------------------------------------------------------- 失败次数限制（按用户名；反向代理后拿不到真实 IP）

_fails: dict[str, list[float]] = {}
_lock = threading.Lock()


def _locked_for(username: str) -> int:
    with _lock:
        recent = [t for t in _fails.get(username, []) if time.time() - t < LOCK_SECONDS]
        _fails[username] = recent
        return int(LOCK_SECONDS - (time.time() - recent[0])) if len(recent) >= MAX_FAILS else 0


def _record_fail(username: str) -> None:
    with _lock:
        _fails.setdefault(username, []).append(time.time())


# ---------------------------------------------------------------- 会话

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(response: Response, request: Request, user: User, remember: bool) -> None:
    token = secrets.token_urlsafe(32)
    days = REMEMBER_DAYS if remember else SESSION_DAYS
    with Session(engine()) as s:
        s.add(AuthSession(token_hash=_token_hash(token), user_id=user.id, expires_at=time.time() + days * 86400))
        u = s.get(User, user.id)
        u.last_login = now()
        s.add(u)
        s.commit()
    response.set_cookie(COOKIE, token, max_age=days * 86400 if remember else None, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https", path="/")


def end_session(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        with Session(engine()) as s:
            row = s.get(AuthSession, _token_hash(token))
            if row:
                s.delete(row)
                s.commit()
    response.delete_cookie(COOKIE, path="/")


def drop_sessions(user_id: int) -> None:
    with Session(engine()) as s:
        for row in s.exec(select(AuthSession).where(AuthSession.user_id == user_id)).all():
            s.delete(row)
        s.commit()


def user_from_request(request: Request) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with Session(engine()) as s:
        row = s.get(AuthSession, _token_hash(token))
        if not row:
            return None
        if row.expires_at < time.time():
            s.delete(row)
            s.commit()
            return None
        u = s.get(User, row.user_id)
        return u if u and not u.disabled else None


# ---------------------------------------------------------------- 账号

def login(username: str, password: str) -> User:
    username = username.strip()
    wait = _locked_for(username)
    if wait:
        raise HTTPException(429, f"密码错误次数过多，请 {wait // 60 + 1} 分钟后再试")
    with Session(engine()) as s:
        u = s.exec(select(User).where(User.username == username)).first()
    if not u or not verify_password(password, u.password_hash):
        _record_fail(username)
        time.sleep(0.5)
        raise HTTPException(401, "用户名或密码不正确")
    if u.disabled:
        raise HTTPException(403, "该账号已被停用，请联系老师")
    _fails.pop(username, None)
    return u


def register(username: str, password: str, invite_code: str, display_name: str = "") -> User:
    code = get_settings().invite_code
    if not code:
        raise HTTPException(403, "当前未开放注册，请联系老师获取账号")
    if not hmac.compare_digest(invite_code.strip().encode(), code.encode()):
        time.sleep(0.5)
        raise HTTPException(400, "邀请码不正确")
    username = username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(400, "用户名为 2~20 位中文、字母、数字或下划线")
    check_password_rule(password)
    with Session(engine()) as s:
        if s.exec(select(User).where(User.username == username)).first():
            raise HTTPException(400, "这个用户名已经被注册了")
        u = User(username=username, display_name=display_name.strip()[:20], password_hash=hash_password(password))
        s.add(u)
        s.commit()
        s.refresh(u)
        return u


def change_password(user: User, old: str, new: str) -> None:
    if not verify_password(old, user.password_hash):
        raise HTTPException(400, "原密码不正确")
    check_password_rule(new)
    with Session(engine()) as s:
        u = s.get(User, user.id)
        u.password_hash = hash_password(new)
        s.add(u)
        s.commit()


def seed_admin() -> None:
    """开启登录时，按环境变量创建或重置管理员账号（忘记密码时改环境变量重启即可）。"""
    st = get_settings()
    if not st.auth_enabled or not st.admin_password:
        return
    with Session(engine()) as s:
        u = s.exec(select(User).where(User.username == st.admin_username)).first() or User(
            username=st.admin_username, display_name="老师", password_hash="")
        if not verify_password(st.admin_password, u.password_hash):
            u.password_hash = hash_password(st.admin_password)
        u.role, u.disabled = "admin", False
        s.add(u)
        s.commit()


def list_users() -> list[dict[str, Any]]:
    with Session(engine()) as s:
        return [public(u) for u in s.exec(select(User).order_by(User.created_at)).all()]


def set_disabled(user_id: int, disabled: bool) -> dict[str, Any]:
    me = current_user.get()
    if me and me.id == user_id:
        raise HTTPException(400, "不能停用自己的账号")
    with Session(engine()) as s:
        u = s.get(User, user_id)
        if not u:
            raise HTTPException(404, "用户不存在")
        u.disabled = disabled
        s.add(u)
        s.commit()
        s.refresh(u)
    if disabled:
        drop_sessions(user_id)
    return public(u)


def delete_user(user_id: int) -> None:
    me = current_user.get()
    if me and me.id == user_id:
        raise HTTPException(400, "不能删除自己的账号")
    with Session(engine()) as s:
        u = s.get(User, user_id)
        if u:
            s.delete(u)
            s.commit()
    drop_sessions(user_id)
