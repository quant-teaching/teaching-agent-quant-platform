"""老师布置作业：给班级布置一个实验任务，并锁定智能体的工作模式、可用工具、策略范围和回测上限。

- 老师（或管理员）在自己管理的班级里布置、修改、删除作业，查看每个学生的完成情况和对话；
- 学生在「作业」页开始作业，会得到一个绑定该作业的对话；在这个对话里，智能体一律按作业锁定的设置工作，
  学生自己在控制面板里的设置不起作用（由后端强制执行）。
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, func, select

from agent.control import Control

from . import auth
from .accounts import _get_class, managed_class_ids
from .db import Assignment, BacktestRecord, ChatMessage, ChatSession, ClassRoom, User, engine


def _me() -> User:
    u = auth.current_user.get()
    if not auth.enabled() or u is None:
        raise HTTPException(400, "作业功能需要开启登录（多人使用模式）")
    return u


def _teacher() -> User:
    u = _me()
    if u.role not in ("admin", "teacher"):
        raise HTTPException(403, "只有老师可以布置和查看作业")
    return u


def _public(a: Assignment, class_name: str = "") -> dict[str, Any]:
    return {"id": a.id, "class_id": a.class_id, "class_name": class_name, "title": a.title, "task": a.task,
            "control": json.loads(a.control_json or "{}"), "due": a.due, "created_at": a.created_at.isoformat()}


def _owned(s: Session, me: User, aid: int) -> Assignment:
    a = s.get(Assignment, aid)
    ids = managed_class_ids(s, me)
    if not a or (ids is not None and a.class_id not in ids):
        raise HTTPException(404, "作业不存在")
    return a


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    title = str(data.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "请填写作业标题")
    return {"title": title[:60], "task": str(data.get("task") or "").strip()[:4000],
            "control_json": json.dumps(Control.parse(data.get("control")).dump(), ensure_ascii=False),
            "due": (str(data["due"])[:10] if data.get("due") else None)}


def create(class_id: int, data: dict[str, Any]) -> dict[str, Any]:
    me = _teacher()
    with Session(engine()) as s:
        room = _get_class(s, me, class_id)
        a = Assignment(class_id=room.id, teacher_id=me.id, **_clean(data))
        s.add(a)
        s.commit()
        s.refresh(a)
        return _public(a, room.name)


def update(aid: int, data: dict[str, Any]) -> dict[str, Any]:
    me = _teacher()
    with Session(engine()) as s:
        a = _owned(s, me, aid)
        for k, v in _clean(data).items():
            setattr(a, k, v)
        s.add(a)
        s.commit()
        s.refresh(a)
        room = s.get(ClassRoom, a.class_id)
        return _public(a, room.name if room else "")


def delete(aid: int) -> None:
    me = _teacher()
    with Session(engine()) as s:
        a = _owned(s, me, aid)
        for cs in s.exec(select(ChatSession).where(ChatSession.assignment_id == aid)).all():
            cs.assignment_id = None  # 学生的对话保留，只是不再绑定作业
            s.add(cs)
        s.delete(a)
        s.commit()


def _progress(s: Session, sid: str) -> dict[str, Any]:
    msgs = s.exec(select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == sid,
                                                                       ChatMessage.role == "user")).one()
    bts = s.exec(select(func.count()).select_from(BacktestRecord).where(BacktestRecord.session_id == sid)).one()
    return {"questions": int(msgs), "backtests": int(bts)}


def list_mine() -> list[dict[str, Any]]:
    me = _me()
    with Session(engine()) as s:
        if me.role == "student":
            if me.class_id is None:
                return []
            room = s.get(ClassRoom, me.class_id)
            rows = s.exec(select(Assignment).where(Assignment.class_id == me.class_id)
                          .order_by(Assignment.created_at.desc())).all()
            out = []
            for a in rows:
                cs = s.exec(select(ChatSession).where(ChatSession.assignment_id == a.id,
                                                      ChatSession.user_id == me.id)).first()
                item = _public(a, room.name if room else "")
                item["mine"] = {"session_id": cs.id, "updated_at": cs.updated_at.isoformat(), **_progress(s, cs.id)} \
                    if cs else None
                out.append(item)
            return out
        ids = managed_class_ids(s, me)
        q = select(Assignment).order_by(Assignment.created_at.desc())
        if ids is not None:
            q = q.where(Assignment.class_id.in_(ids or {-1}))
        names = {c.id: c.name for c in s.exec(select(ClassRoom)).all()}
        out = []
        for a in s.exec(q).all():
            total = s.exec(select(func.count()).select_from(User).where(User.class_id == a.class_id,
                                                                         User.role == "student")).one()
            started = s.exec(select(func.count()).select_from(ChatSession).where(
                ChatSession.assignment_id == a.id)).one()
            out.append({**_public(a, names.get(a.class_id, "")), "students": int(total), "started": int(started)})
        return out


def detail(aid: int) -> dict[str, Any]:
    me = _teacher()
    with Session(engine()) as s:
        a = _owned(s, me, aid)
        room = s.get(ClassRoom, a.class_id)
        students = s.exec(select(User).where(User.class_id == a.class_id, User.role == "student")
                          .order_by(User.username)).all()
        sessions = {cs.user_id: cs for cs in s.exec(select(ChatSession).where(ChatSession.assignment_id == aid)).all()}
        rows = []
        for u in students:
            cs = sessions.get(u.id)
            rows.append({"user_id": u.id, "username": u.username, "display_name": u.display_name or u.username,
                         "session_id": cs.id if cs else None, "updated_at": cs.updated_at.isoformat() if cs else None,
                         **(_progress(s, cs.id) if cs else {"questions": 0, "backtests": 0})})
        rows.sort(key=lambda r: (r["session_id"] is None, -(r["questions"] or 0), r["username"]))  # 已开始的排前面
        return {**_public(a, room.name if room else ""), "rows": rows}


def start(aid: int) -> dict[str, Any]:
    """学生开始（或继续）作业：返回绑定该作业的对话。老师也可以试做自己布置的作业。"""
    me = _me()
    with Session(engine()) as s:
        a = s.get(Assignment, aid)
        if not a:
            raise HTTPException(404, "作业不存在")
        if me.role == "student" and me.class_id != a.class_id:
            raise HTTPException(404, "作业不存在")
        if me.role in ("admin", "teacher"):
            _owned(s, me, aid)
        cs = s.exec(select(ChatSession).where(ChatSession.assignment_id == aid, ChatSession.user_id == me.id)).first()
        if not cs:
            cs = ChatSession(id=uuid.uuid4().hex[:12], user_id=me.id, assignment_id=aid, title=f"作业：{a.title}"[:30])
            s.add(cs)
            s.commit()
            s.refresh(cs)
        return {"session_id": cs.id}


def student_session(aid: int, session_id: str) -> dict[str, Any]:
    """老师查看学生的作业对话（只读）。"""
    me = _teacher()
    with Session(engine()) as s:
        a = _owned(s, me, aid)
        cs = s.get(ChatSession, session_id)
        if not cs or cs.assignment_id != a.id:
            raise HTTPException(404, "对话不存在")
        owner = s.get(User, cs.user_id) if cs.user_id else None
        msgs = s.exec(select(ChatMessage).where(ChatMessage.session_id == cs.id).order_by(ChatMessage.id)).all()
        return {"id": cs.id, "title": cs.title, "student": owner.display_name or owner.username if owner else "",
                "messages": [{"id": m.id, "role": m.role, "content": m.content, "events": json.loads(m.events_json),
                              "model": m.model, "created_at": m.created_at.isoformat()} for m in msgs]}


def for_session(session_id: str) -> dict[str, Any] | None:
    """对话绑定的作业（智能体据此锁定设置、补充作业说明）。"""
    with Session(engine()) as s:
        cs = s.get(ChatSession, session_id)
        if not cs or not cs.assignment_id:
            return None
        a = s.get(Assignment, cs.assignment_id)
        return _public(a) if a else None
