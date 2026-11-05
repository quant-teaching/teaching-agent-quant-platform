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

from .db import AuthSession, ClassRoom, User, engine, get_setting, now, set_setting
from .settings import get_settings

COOKIE = "qt_session"
SESSION_DAYS, REMEMBER_DAYS = 1, 30
MAX_FAILS, LOCK_SECONDS = 5, 300
USERNAME_RE = re.compile(r"^[A-Za-z0-9_一-龥]{2,20}$")
INVITE_KEY = "auth.invite"  # 旧版本的全局邀请码，启动时迁移为「默认班级」的邀请码
TEACHER_INVITE_KEY = "auth.teacher_invite"
ROLE_LABELS = {"admin": "管理员", "teacher": "老师", "student": "学生"}
INVITE_RE = re.compile(r"^[A-Za-z0-9_-]{4,40}$")

current_user: ContextVar[User | None] = ContextVar("current_user", default=None)


def enabled() -> bool:
    return get_settings().auth_enabled


def current_user_id() -> int | None:
    u = current_user.get()
    return u.id if u else None


def is_admin() -> bool:
    u = current_user.get()
    return bool(u and u.role == "admin")


def is_teacher() -> bool:
    """老师或管理员：可以管理班级和学生。"""
    u = current_user.get()
    return bool(u and u.role in ("admin", "teacher"))


def public(u: User, class_name: str | None = None) -> dict[str, Any]:
    return {"id": u.id, "username": u.username, "display_name": u.display_name or u.username, "role": u.role,
            "role_label": ROLE_LABELS.get(u.role, u.role), "class_id": u.class_id, "class_name": class_name,
            "disabled": u.disabled, "created_at": u.created_at.isoformat(),
            "last_login": u.last_login.isoformat() if u.last_login else None}


def public_with_class(u: User) -> dict[str, Any]:
    name = None
    if u.class_id:
        with Session(engine()) as s:
            c = s.get(ClassRoom, u.class_id)
            name = c.name if c else None
    return public(u, name)


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


# ---------------------------------------------------------------- 注册：学生凭班级邀请码，老师凭教师注册码

def teacher_invite_config() -> dict[str, Any]:
    """教师注册码：管理员在页面上设置；未设置时沿用环境变量 TEACHER_INVITE_CODE（为空则不开放老师注册）。"""
    saved = get_setting(TEACHER_INVITE_KEY)
    if saved is None:
        code = get_settings().teacher_invite_code
        return {"code": code, "enabled": bool(code), "source": "env"}
    return {"code": saved.get("code", ""), "enabled": bool(saved.get("enabled")) and bool(saved.get("code")),
            "source": "db"}


def set_teacher_invite(code: str, enabled: bool) -> dict[str, Any]:
    code = code.strip()
    if (enabled or code) and not INVITE_RE.match(code):
        raise HTTPException(400, "注册码为 4~40 位字母、数字、下划线或短横线")
    with Session(engine()) as s:
        if code and s.exec(select(ClassRoom).where(ClassRoom.invite_code == code)).first():
            raise HTTPException(400, "这个注册码和某个班级的邀请码相同，请换一个")
    set_setting(TEACHER_INVITE_KEY, {"code": code, "enabled": enabled})
    return teacher_invite_config()


def registration_status() -> dict[str, bool]:
    """登录页显示哪些注册入口。"""
    with Session(engine()) as s:
        student = s.exec(select(ClassRoom).where(ClassRoom.registration_open == True)).first() is not None  # noqa: E712
    return {"student": student, "teacher": teacher_invite_config()["enabled"]}


def _check_username(s: Session, username: str) -> str:
    username = username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(400, "用户名为 2~20 位中文、字母、数字或下划线")
    if s.exec(select(User).where(User.username == username)).first():
        raise HTTPException(400, "这个用户名已经被注册了")
    return username


def register(username: str, password: str, invite_code: str, display_name: str = "",
             as_role: str = "student") -> User:
    code = invite_code.strip()
    check_password_rule(password)
    with Session(engine()) as s:
        if as_role == "teacher":
            t = teacher_invite_config()
            if not t["enabled"]:
                raise HTTPException(403, "当前未开放老师注册，请联系平台管理员")
            if not hmac.compare_digest(code.encode(), t["code"].encode()):
                time.sleep(0.5)
                raise HTTPException(400, "教师注册码不正确")
            role, class_id = "teacher", None
        else:
            if not registration_status()["student"]:
                raise HTTPException(403, "当前未开放注册，请联系老师获取账号")
            room = s.exec(select(ClassRoom).where(ClassRoom.invite_code == code)).first() if code else None
            if not room:
                time.sleep(0.5)
                raise HTTPException(400, "班级邀请码不正确")
            if not room.registration_open:
                raise HTTPException(403, f"「{room.name}」已关闭注册，请联系老师")
            role, class_id = "student", room.id
        username = _check_username(s, username)
        u = User(username=username, display_name=display_name.strip()[:20], password_hash=hash_password(password),
                 role=role, class_id=class_id)
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
    """开启登录时，按环境变量创建或重置管理员账号（忘记密码时改环境变量重启即可），并迁移旧数据。"""
    st = get_settings()
    if not st.auth_enabled:
        return
    admin_id = None
    with Session(engine()) as s:
        if st.admin_password:
            u = s.exec(select(User).where(User.username == st.admin_username)).first() or User(
                username=st.admin_username, display_name="管理员", password_hash="")
            if not verify_password(st.admin_password, u.password_hash):
                u.password_hash = hash_password(st.admin_password)
            u.role, u.disabled, u.class_id = "admin", False, None
            s.add(u)
            s.commit()
            s.refresh(u)
            admin_id = u.id
    migrate_default_class(admin_id)


def migrate_default_class(admin_id: int | None) -> None:
    """旧版本只有一个全局邀请码、学生不分班。第一次升级时建一个「默认班级」：
    邀请码沿用原来的全局邀请码（学生手里的码继续有效），没有班级的学生全部归入这个班。"""
    with Session(engine()) as s:
        orphans = s.exec(select(User).where(User.role == "student", User.class_id == None)).all()  # noqa: E711
        has_class = s.exec(select(ClassRoom)).first() is not None
        saved = get_setting(INVITE_KEY)
        old_code = (saved or {}).get("code") if saved is not None else get_settings().invite_code
        old_open = bool((saved or {}).get("enabled")) if saved is not None else bool(old_code)
        if has_class and not orphans:
            return
        if not has_class and not old_code and not orphans:
            return
        room = s.exec(select(ClassRoom).where(ClassRoom.name == "默认班级")).first()
        if room is None:
            code = old_code if old_code and INVITE_RE.match(old_code) else "class-" + secrets.token_hex(3)
            room = ClassRoom(name="默认班级", description="升级前注册的学生", teacher_id=admin_id, invite_code=code,
                             registration_open=old_open)
            s.add(room)
            s.commit()
            s.refresh(room)
        for u in orphans:
            u.class_id = room.id
            s.add(u)
        s.commit()
