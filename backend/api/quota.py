"""平台模型使用额度：按"每天对话次数"计算（发送一条消息算一次）。

生效顺序：个人设置 > 班级默认（学生）> 角色默认（管理员在设置页配置）。管理员不受限制。
只有使用平台渠道时才计次；用户自己添加的模型渠道不占用额度。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from .db import ClassRoom, ModelUsage, User, engine, get_setting, set_setting

DEFAULTS_KEY = "quota.defaults"
DEFAULTS = {"teacher": None, "student": 50}  # None 表示不限
MAX_DAILY = 100000


def _today() -> str:
    return date.today().isoformat()


def defaults() -> dict[str, int | None]:
    return {**DEFAULTS, **(get_setting(DEFAULTS_KEY) or {})}


def set_defaults(teacher: int | None, student: int | None) -> dict[str, int | None]:
    for v in (teacher, student):
        if v is not None and not 0 <= v <= MAX_DAILY:
            raise HTTPException(400, f"每日次数应在 0~{MAX_DAILY} 之间，留空表示不限")
    set_setting(DEFAULTS_KEY, {"teacher": teacher, "student": student})
    return defaults()


def check_value(v: int | None) -> None:
    if v is not None and not 0 <= v <= MAX_DAILY:
        raise HTTPException(400, f"每日次数应在 0~{MAX_DAILY} 之间，留空表示沿用默认值")


def effective(u: User, s: Session | None = None) -> tuple[int | None, str]:
    """返回 (每日上限, 来源说明)；上限为 None 表示不限。"""
    if u.role == "admin":
        return None, "管理员不限"
    if u.quota_daily is not None:
        return u.quota_daily, "个人设置"
    if u.role == "student" and u.class_id:
        own = s or Session(engine())
        try:
            room = own.get(ClassRoom, u.class_id)
        finally:
            if s is None:
                own.close()
        if room and room.quota_daily is not None:
            return room.quota_daily, "班级默认"
    return defaults().get(u.role), "角色默认"


def used_today(user_id: int, s: Session | None = None) -> int:
    own = s or Session(engine())
    try:
        row = own.exec(select(ModelUsage).where(ModelUsage.user_id == user_id, ModelUsage.day == _today())).first()
        return row.count if row else 0
    finally:
        if s is None:
            own.close()


def status(u: User) -> dict[str, Any]:
    with Session(engine()) as s:
        limit, source = effective(u, s)
        used = used_today(u.id, s)
    return {"limit": limit, "used": used, "remaining": None if limit is None else max(limit - used, 0), "source": source}


def consume(u: User) -> None:
    """开始一轮使用平台模型的对话前调用：超出额度时拒绝，否则计一次。"""
    with Session(engine()) as s:
        limit, _ = effective(u, s)
        row = s.exec(select(ModelUsage).where(ModelUsage.user_id == u.id, ModelUsage.day == _today())).first()
        used = row.count if row else 0
        if limit is not None and used >= limit:
            raise HTTPException(429, f"今天的平台模型对话次数已用完（{used} / {limit}），明天会自动恢复；"
                                     "如需更多次数请联系老师，也可以在「设置 → 我的模型」添加自己的模型渠道")
        row = row or ModelUsage(user_id=u.id, day=_today(), count=0)
        row.count += 1
        s.add(row)
        s.commit()
