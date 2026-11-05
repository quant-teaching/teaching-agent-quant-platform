"""班级与账号管理：老师管理自己的班级和学生，管理员管理全部账号。

权限：
- 管理员（admin）：所有班级、所有账号，可以指定班级的负责老师、修改角色；
- 老师（teacher）：只能看到和管理自己创建（负责）的班级，以及这些班级里的学生；
- 学生（student）：只能管理自己的账号（个人设置页）。
班级之间互相隔离：学生只属于一个班级，老师看不到别人班级的学生和记录。
"""

from __future__ import annotations

import base64
import csv
import io
import secrets

from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, func, select

from . import auth, quota
from .db import AuthSession, BacktestRecord, ChatSession, ClassRoom, InviteCode, LLMProvider, User, engine, now

ROLES = ("admin", "teacher", "student")
IMPORT_COLUMNS = ("用户名", "姓名", "初始密码")
MAX_IMPORT = 500


# ---------------------------------------------------------------- 权限

def _me() -> User:
    u = auth.current_user.get()
    if not u or u.role not in ("admin", "teacher"):
        raise HTTPException(403, "只有老师或管理员可以管理班级和学生")
    return u


def _require_admin() -> User:
    u = auth.current_user.get()
    if not u or u.role != "admin":
        raise HTTPException(403, "只有管理员可以进行这项操作")
    return u


def managed_class_ids(s: Session, me: User) -> set[int] | None:
    """me 能管理的班级 id；None 表示全部（管理员）。"""
    if me.role == "admin":
        return None
    return set(s.exec(select(ClassRoom.id).where(ClassRoom.teacher_id == me.id)).all())


def _get_class(s: Session, me: User, class_id: int) -> ClassRoom:
    room = s.get(ClassRoom, class_id)
    ids = managed_class_ids(s, me)
    if not room or (ids is not None and room.id not in ids):
        raise HTTPException(404, "班级不存在")
    return room


def _get_user(s: Session, me: User, user_id: int) -> User:
    u = s.get(User, user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    if me.role == "admin":
        return u
    ids = managed_class_ids(s, me)
    if u.role != "student" or u.class_id not in ids:
        raise HTTPException(404, "用户不存在")
    return u


def can_view_owner(owner_id: int | None) -> bool:
    """能否查看某个用户的回测报告：本人、管理员、该学生所在班级的老师、同班同学。"""
    if not auth.enabled() or owner_id is None:
        return True
    me = auth.current_user.get()
    if not me:
        return False
    if me.id == owner_id or me.role == "admin":
        return True
    with Session(engine()) as s:
        owner = s.get(User, owner_id)
        if not owner or owner.class_id is None:
            return False
        if me.role == "teacher":
            room = s.get(ClassRoom, owner.class_id)
            return bool(room and room.teacher_id == me.id)
        return me.class_id == owner.class_id


# ---------------------------------------------------------------- 工具

def gen_password(n: int = 8) -> str:
    """初始密码：字母加数字，去掉容易看错的 0 / O / 1 / l / I。"""
    letters = "abcdefghjkmnpqrstuvwxyz"
    digits = "23456789"
    while True:
        pw = "".join(secrets.choice(letters + digits) for _ in range(n))
        if any(c in digits for c in pw) and any(c in letters for c in pw):
            return pw


def gen_class_code() -> str:
    abc = "abcdefghjkmnpqrstuvwxyz23456789"
    return "class-" + "".join(secrets.choice(abc) for _ in range(6))


def _unique_code(s: Session) -> str:
    for _ in range(20):
        code = gen_class_code()
        if not s.exec(select(ClassRoom).where(ClassRoom.invite_code == code)).first() \
                and code != auth.teacher_invite_config()["code"]:
            return code
    raise HTTPException(500, "生成邀请码失败，请重试")


def _class_names(s: Session) -> dict[int, str]:
    return {c.id: c.name for c in s.exec(select(ClassRoom)).all()}


def _user_names(s: Session) -> dict[int, str]:
    return {u.id: (u.display_name or u.username) for u in s.exec(select(User)).all()}


# ---------------------------------------------------------------- 班级

def class_public(s: Session, room: ClassRoom, teachers: dict[int, str] | None = None) -> dict[str, Any]:
    students = s.exec(select(User).where(User.class_id == room.id, User.role == "student")).all()
    ids = [u.id for u in students]
    week = now() - timedelta(days=7)
    backtests = s.exec(select(func.count()).select_from(BacktestRecord).where(BacktestRecord.user_id.in_(ids))).one() \
        if ids else 0
    teachers = teachers if teachers is not None else _user_names(s)
    return {
        "id": room.id, "name": room.name, "description": room.description,
        "teacher_id": room.teacher_id, "teacher_name": teachers.get(room.teacher_id) if room.teacher_id else None,
        "invite_code": room.invite_code, "registration_open": room.registration_open,
        "created_at": room.created_at.isoformat(),
        "quota_daily": room.quota_daily,
        "student_count": len(students),
        "disabled_count": sum(1 for u in students if u.disabled),
        "active_7d": sum(1 for u in students if u.last_login and u.last_login >= week),
        "backtest_count": int(backtests),
    }


def list_classes() -> list[dict[str, Any]]:
    me = _me()
    with Session(engine()) as s:
        q = select(ClassRoom).order_by(ClassRoom.created_at)
        if me.role != "admin":
            q = q.where(ClassRoom.teacher_id == me.id)
        names = _user_names(s)
        return [class_public(s, r, names) for r in s.exec(q).all()]


def create_class(name: str, description: str = "", teacher_id: int | None = None) -> dict[str, Any]:
    me = _me()
    name = name.strip()
    if not name or len(name) > 30:
        raise HTTPException(400, "班级名称为 1~30 个字")
    with Session(engine()) as s:
        owner = me.id
        if teacher_id is not None and me.role == "admin":
            t = s.get(User, teacher_id)
            if not t or t.role not in ("teacher", "admin"):
                raise HTTPException(400, "负责老师不存在")
            owner = t.id
        if s.exec(select(ClassRoom).where(ClassRoom.name == name, ClassRoom.teacher_id == owner)).first():
            raise HTTPException(400, "你已经有一个同名的班级了")
        room = ClassRoom(name=name, description=description.strip()[:100], teacher_id=owner, invite_code=_unique_code(s))
        s.add(room)
        s.commit()
        s.refresh(room)
        return class_public(s, room)


def update_class(class_id: int, data: dict[str, Any]) -> dict[str, Any]:
    me = _me()
    with Session(engine()) as s:
        room = _get_class(s, me, class_id)
        if data.get("name") is not None:
            name = data["name"].strip()
            if not name or len(name) > 30:
                raise HTTPException(400, "班级名称为 1~30 个字")
            room.name = name
        if data.get("description") is not None:
            room.description = data["description"].strip()[:100]
        if data.get("registration_open") is not None:
            room.registration_open = bool(data["registration_open"])
        if data.get("invite_code") is not None:
            code = data["invite_code"].strip()
            if not auth.INVITE_RE.match(code):
                raise HTTPException(400, "邀请码为 4~40 位字母、数字、下划线或短横线")
            other = s.exec(select(ClassRoom).where(ClassRoom.invite_code == code)).first()
            if (other and other.id != room.id) or code == auth.teacher_invite_config()["code"]:
                raise HTTPException(400, "这个邀请码已经被使用，请换一个")
            room.invite_code = code
        if "quota_daily" in data:  # 显式传 null 表示沿用角色默认值
            quota.check_value(data["quota_daily"])
            room.quota_daily = data["quota_daily"]
        if data.get("teacher_id") is not None:
            if me.role != "admin":
                raise HTTPException(403, "只有管理员可以更换班级的负责老师")
            t = s.get(User, data["teacher_id"])
            if not t or t.role not in ("teacher", "admin"):
                raise HTTPException(400, "负责老师不存在")
            room.teacher_id = t.id
        s.add(room)
        s.commit()
        s.refresh(room)
        return class_public(s, room)


def regenerate_code(class_id: int) -> dict[str, Any]:
    me = _me()
    with Session(engine()) as s:
        room = _get_class(s, me, class_id)
        room.invite_code = _unique_code(s)
        s.add(room)
        s.commit()
        s.refresh(room)
        return class_public(s, room)


def delete_class(class_id: int) -> None:
    me = _me()
    with Session(engine()) as s:
        room = _get_class(s, me, class_id)
        if s.exec(select(User).where(User.class_id == room.id)).first():
            raise HTTPException(400, "班级里还有学生，请先把学生移到其他班级或删除后再删除班级")
        s.delete(room)
        s.commit()


def class_activity(class_id: int, days: int = 30) -> dict[str, Any]:
    """班级可视化：最近 days 天每天的回测次数和活跃人数，以及每个学生的回测次数。"""
    me = _me()
    with Session(engine()) as s:
        room = _get_class(s, me, class_id)
        students = s.exec(select(User).where(User.class_id == room.id, User.role == "student")).all()
        ids = [u.id for u in students]
        since = now() - timedelta(days=days)
        rows = s.exec(select(BacktestRecord.user_id, BacktestRecord.created_at)
                      .where(BacktestRecord.user_id.in_(ids), BacktestRecord.created_at >= since)).all() if ids else []
    daily: dict[str, set[int]] = {}
    count: dict[str, int] = {}
    for uid, at in rows:
        d = at.date().isoformat()
        daily.setdefault(d, set()).add(uid)
        count[d] = count.get(d, 0) + 1
    dates = [(now() - timedelta(days=i)).date().isoformat() for i in range(days - 1, -1, -1)]
    return {"dates": dates, "backtests": [count.get(d, 0) for d in dates],
            "active": [len(daily.get(d, ())) for d in dates]}


# ---------------------------------------------------------------- 用户

def _user_row(s: Session, u: User, classes: dict[int, str]) -> dict[str, Any]:
    d = auth.public(u, classes.get(u.class_id) if u.class_id else None)
    d["backtest_count"] = int(s.exec(select(func.count()).select_from(BacktestRecord)
                                     .where(BacktestRecord.user_id == u.id)).one())
    d["chat_count"] = int(s.exec(select(func.count()).select_from(ChatSession).where(ChatSession.user_id == u.id)).one())
    limit, source = quota.effective(u, s)
    d.update(quota_daily=u.quota_daily, allow_platform=u.allow_platform, allow_own=u.allow_own,
             quota={"limit": limit, "used": quota.used_today(u.id, s), "source": source},
             own_channels=len(s.exec(select(LLMProvider.id).where(LLMProvider.owner_id == u.id)).all()))
    return d


def list_users(role: str | None = None, class_id: int | None = None, q: str | None = None) -> list[dict[str, Any]]:
    me = _me()
    with Session(engine()) as s:
        stmt = select(User).order_by(User.created_at)
        ids = managed_class_ids(s, me)
        if ids is not None:  # 老师只能看到自己班级的学生
            stmt = stmt.where(User.role == "student", User.class_id.in_(ids or {-1}))
        if role:
            stmt = stmt.where(User.role == role)
        if class_id is not None:
            stmt = stmt.where(User.class_id == class_id)
        rows = s.exec(stmt).all()
        if q:
            k = q.strip().lower()
            rows = [u for u in rows if k in u.username.lower() or k in (u.display_name or "").lower()]
        classes = _class_names(s)
        return [_user_row(s, u, classes) for u in rows]


def create_user(username: str, display_name: str = "", password: str = "", role: str = "student",
                class_id: int | None = None) -> dict[str, Any]:
    me = _me()
    if role not in ROLES:
        raise HTTPException(400, "角色不正确")
    if me.role != "admin" and role != "student":
        raise HTTPException(403, "老师只能创建学生账号")
    pw = password or gen_password()
    auth.check_password_rule(pw)
    with Session(engine()) as s:
        if role == "student":
            if class_id is None:
                raise HTTPException(400, "学生账号需要选择班级")
            _get_class(s, me, class_id)
        else:
            class_id = None
        username = auth._check_username(s, username)
        u = User(username=username, display_name=display_name.strip()[:20], password_hash=auth.hash_password(pw),
                 role=role, class_id=class_id)
        s.add(u)
        s.commit()
        s.refresh(u)
        out = _user_row(s, u, _class_names(s))
    out["initial_password"] = pw
    return out


def update_user(user_id: int, data: dict[str, Any]) -> dict[str, Any]:
    me = _me()
    with Session(engine()) as s:
        u = _get_user(s, me, user_id)
        if data.get("display_name") is not None:
            u.display_name = data["display_name"].strip()[:20]
        if data.get("role") is not None and data["role"] != u.role:
            if me.role != "admin":
                raise HTTPException(403, "只有管理员可以修改角色")
            if u.id == me.id:
                raise HTTPException(400, "不能修改自己的角色")
            if data["role"] not in ROLES:
                raise HTTPException(400, "角色不正确")
            u.role = data["role"]
            if u.role != "student":
                u.class_id = None
        if "class_id" in data and data["class_id"] is not None and u.role == "student":
            _get_class(s, me, data["class_id"])
            u.class_id = data["class_id"]
        if data.get("disabled") is not None:
            if u.id == me.id:
                raise HTTPException(400, "不能停用自己的账号")
            u.disabled = bool(data["disabled"])
        if "quota_daily" in data:  # 显式传 null 表示沿用班级或角色默认值
            quota.check_value(data["quota_daily"])
            u.quota_daily = data["quota_daily"]
        if data.get("allow_platform") is not None:  # 老师可以开关本班学生使用平台模型
            u.allow_platform = bool(data["allow_platform"])
        if data.get("allow_own") is not None:
            if me.role != "admin":
                raise HTTPException(403, "只有管理员可以开关「使用自己的模型渠道」")
            u.allow_own = bool(data["allow_own"])
        if u.role == "student" and u.class_id is None:
            raise HTTPException(400, "学生账号需要属于一个班级")
        s.add(u)
        s.commit()
        s.refresh(u)
        if u.disabled:
            auth.drop_sessions(u.id)
        return _user_row(s, u, _class_names(s))


def reset_password(user_id: int, password: str = "") -> dict[str, Any]:
    me = _me()
    pw = password or gen_password()
    auth.check_password_rule(pw)
    with Session(engine()) as s:
        u = _get_user(s, me, user_id)
        if u.role == "admin" and u.id != me.id:
            raise HTTPException(403, "不能重置其他管理员的密码")
        u.password_hash = auth.hash_password(pw)
        s.add(u)
        s.commit()
    auth.drop_sessions(user_id)  # 重置后对方需要用新密码重新登录
    return {"ok": True, "password": pw}


def delete_user(user_id: int) -> None:
    me = _me()
    with Session(engine()) as s:
        u = _get_user(s, me, user_id)
        if u.id == me.id:
            raise HTTPException(400, "不能删除自己的账号")
        if u.role in ("admin", "teacher"):
            if me.role != "admin":
                raise HTTPException(403, "只有管理员可以删除老师账号")
            if s.exec(select(ClassRoom).where(ClassRoom.teacher_id == u.id)).first():
                raise HTTPException(400, "这位老师还负责着班级，请先把班级转给其他老师")
        s.delete(u)
        for row in s.exec(select(AuthSession).where(AuthSession.user_id == user_id)).all():
            s.delete(row)
        s.commit()


def user_backtests(user_id: int, limit: int = 100) -> list[dict[str, Any]]:
    """老师查看学生的回测记录（只读）。"""
    import json
    me = _me()
    with Session(engine()) as s:
        _get_user(s, me, user_id)
        rows = s.exec(select(BacktestRecord).where(BacktestRecord.user_id == user_id)
                      .order_by(BacktestRecord.created_at.desc()).limit(limit)).all()
    return [{"id": r.id, "kind": r.kind, "title": r.title, "start": r.start, "end": r.end, "source": r.source,
             "summary": json.loads(r.summary_json), "created_at": r.created_at.isoformat()} for r in rows]


# ---------------------------------------------------------------- 批量导入

def import_template() -> bytes:
    """学生名单模板（CSV，带 BOM，Excel 直接打开）。初始密码可以留空，由系统自动生成。"""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(IMPORT_COLUMNS)
    w.writerow(["zhangsan01", "张三", ""])
    w.writerow(["lisi02", "李四", "study2026"])
    w.writerow(["王五", "王五", ""])
    return buf.getvalue().encode("utf-8-sig")


def _read_rows(filename: str, content: bytes) -> list[list[str]]:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001 - 文件损坏或不是 Excel
            raise HTTPException(400, "无法读取这个 Excel 文件，请确认是 .xlsx 格式") from e
        ws = wb.worksheets[0]
        return [["" if v is None else str(v).strip() for v in row] for row in ws.iter_rows(values_only=True)]
    if name.endswith(".xls"):
        raise HTTPException(400, "不支持旧版 .xls 文件，请在 Excel 中另存为 .xlsx 或 .csv")
    for enc in ("utf-8-sig", "gbk"):  # Excel 另存为 CSV 时常是 GBK 编码
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise HTTPException(400, "无法识别文件编码，请另存为 UTF-8 或 GBK 编码的 CSV")
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(text))]


def import_students(class_id: int, filename: str, content_b64: str, dry_run: bool = True) -> dict[str, Any]:
    """解析名单并校验；dry_run 只返回预览，否则创建账号并返回每个人的初始密码。"""
    me = _me()
    try:
        content = base64.b64decode(content_b64)
    except ValueError as e:
        raise HTTPException(400, "文件内容无法解析") from e
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(400, "文件太大（超过 2 MB）")
    rows = [r for r in _read_rows(filename, content) if any(c for c in r)]
    if not rows:
        raise HTTPException(400, "文件是空的")
    header = rows[0]
    col = {name: header.index(name) for name in IMPORT_COLUMNS if name in header}
    if "用户名" not in col:
        raise HTTPException(400, "第一行需要是表头，至少包含「用户名」一列（可以下载模板对照）")
    body = rows[1:]
    if len(body) > MAX_IMPORT:
        raise HTTPException(400, f"一次最多导入 {MAX_IMPORT} 人")
    get = lambda r, k: (r[col[k]].strip() if k in col and col[k] < len(r) else "")  # noqa: E731
    with Session(engine()) as s:
        room = _get_class(s, me, class_id)
        existing = {u.username for u in s.exec(select(User)).all()}
        seen: set[str] = set()
        out = []
        for i, r in enumerate(body, start=2):
            username, name, pw = get(r, "用户名"), get(r, "姓名"), get(r, "初始密码")
            err = None
            if not auth.USERNAME_RE.match(username):
                err = "用户名需为 2~20 位中文、字母、数字或下划线"
            elif username in existing:
                err = "用户名已存在"
            elif username in seen:
                err = "与表格中前面的行重复"
            elif pw:
                try:
                    auth.check_password_rule(pw)
                except HTTPException as e:
                    err = str(e.detail)
            seen.add(username)
            out.append({"row": i, "username": username, "display_name": name[:20], "password": pw, "error": err})
        ok = [x for x in out if not x["error"]]
        if not dry_run:
            if not ok:
                raise HTTPException(400, "没有可以导入的行")
            for x in ok:
                x["password"] = x["password"] or gen_password()
                s.add(User(username=x["username"], display_name=x["display_name"],
                           password_hash=auth.hash_password(x["password"]), role="student", class_id=room.id))
            s.commit()
        else:
            for x in out:  # 预览时不显示密码，只提示是否自动生成
                x["password"] = "（自动生成）" if not x["password"] else "（使用表格中的密码）"
        return {"class_name": room.name, "total": len(out), "valid": len(ok), "rows": out, "created": not dry_run}




# ---------------------------------------------------------------- 一次性注册码

ONCE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 去掉 0/O、1/I/L 等容易看错的字符


def gen_once_code() -> str:
    raw = "".join(secrets.choice(ONCE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def _code_public(c: InviteCode, names: dict[int, str]) -> dict[str, Any]:
    state = "revoked" if c.revoked else ("used" if c.used_by else "unused")
    return {"code": c.code, "kind": c.kind, "class_id": c.class_id, "note": c.note, "state": state,
            "created_at": c.created_at.isoformat(), "used_by": c.used_by,
            "used_by_name": names.get(c.used_by) if c.used_by else None,
            "used_at": c.used_at.isoformat() if c.used_at else None}


def _check_code_scope(s: Session, me: User, kind: str, class_id: int | None) -> None:
    if kind == "teacher":
        if me.role != "admin":
            raise HTTPException(403, "只有管理员可以生成教师注册码")
    elif kind == "student":
        if class_id is None:
            raise HTTPException(400, "学生注册码需要指定班级")
        _get_class(s, me, class_id)
    else:
        raise HTTPException(400, "注册码类型不正确")


def create_codes(kind: str, class_id: int | None, count: int, note: str = "") -> list[dict[str, Any]]:
    me = _me()
    if not 1 <= count <= 200:
        raise HTTPException(400, "一次可以生成 1~200 个")
    with Session(engine()) as s:
        _check_code_scope(s, me, kind, class_id)
        made = []
        while len(made) < count:
            code = gen_once_code()
            if s.get(InviteCode, code):
                continue
            row = InviteCode(code=code, kind=kind, class_id=class_id if kind == "student" else None,
                             note=note.strip()[:40], created_by=me.id)
            s.add(row)
            made.append(row)
        s.commit()
        return [_code_public(c, {}) for c in made]


def list_codes(kind: str, class_id: int | None = None) -> list[dict[str, Any]]:
    me = _me()
    with Session(engine()) as s:
        _check_code_scope(s, me, kind, class_id)
        q = select(InviteCode).where(InviteCode.kind == kind).order_by(InviteCode.created_at.desc())
        if kind == "student":
            q = q.where(InviteCode.class_id == class_id)
        names = _user_names(s)
        return [_code_public(c, names) for c in s.exec(q).all()]


def revoke_code(code: str) -> None:
    me = _me()
    with Session(engine()) as s:
        row = s.get(InviteCode, code.strip().upper())
        if not row:
            raise HTTPException(404, "注册码不存在")
        _check_code_scope(s, me, row.kind, row.class_id)
        if row.used_by:
            raise HTTPException(400, "已经使用过的注册码不需要作废")
        row.revoked = True
        s.add(row)
        s.commit()
