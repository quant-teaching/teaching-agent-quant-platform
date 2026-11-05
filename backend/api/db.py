"""SQLite 数据表：模型接口、应用设置、对话会话与消息、回测记录、衍生策略。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from sqlalchemy import Column, Text, event
from sqlmodel import Field, Session, SQLModel, create_engine, select

from .settings import get_settings


def now() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


class LLMProvider(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    base_url: str
    api_key: str = ""
    models_json: str = Field(default="[]", sa_column=Column(Text))  # 拉取到的模型列表缓存
    enabled: bool = True
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    @property
    def models(self) -> list[str]:
        return json.loads(self.models_json or "[]")


class AppSetting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = Field(sa_column=Column(Text))


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    display_name: str = ""
    password_hash: str
    role: str = "student"  # admin 平台管理员 / teacher 老师 / student 学生
    class_id: int | None = Field(default=None, index=True)  # 学生所属班级；老师和管理员为空
    disabled: bool = False
    created_at: datetime = Field(default_factory=now)
    last_login: datetime | None = None


class ClassRoom(SQLModel, table=True):
    """班级：由老师创建，学生凭班级邀请码注册进入；不同班级的数据互相隔离。"""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    teacher_id: int | None = Field(default=None, index=True)  # 负责老师；为空表示由管理员管理
    invite_code: str = Field(index=True, unique=True)
    registration_open: bool = True
    created_at: datetime = Field(default_factory=now)


class AuthSession(SQLModel, table=True):
    token_hash: str = Field(primary_key=True)  # 只存令牌的 SHA-256，数据库泄露也拿不到可用的登录态
    user_id: int = Field(index=True)
    expires_at: float  # Unix 时间戳
    created_at: datetime = Field(default_factory=now)


class ChatSession(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: int | None = Field(default=None, index=True)  # 开启登录后按用户隔离
    title: str = "新对话"
    state_json: str = Field(default="{}", sa_column=Column(Text))  # 工作参数、最近回测等
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    role: str  # user / assistant
    content: str = Field(default="", sa_column=Column(Text))
    events_json: str = Field(default="[]", sa_column=Column(Text))  # 前端展示用的工具卡片等
    llm_json: str = Field(default="[]", sa_column=Column(Text))  # 本轮发给模型的消息（含工具调用），用于上下文
    model: str | None = None
    created_at: datetime = Field(default_factory=now)


class BacktestRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    kind: str  # single / portfolio
    title: str
    strategy_id: str
    category: str
    start: str
    end: str
    summary_json: str = Field(default="{}", sa_column=Column(Text))
    params_json: str = Field(default="{}", sa_column=Column(Text))
    universe_label: str = ""
    session_id: str | None = Field(default=None, index=True)
    user_id: int | None = Field(default=None, index=True)
    source: str = "manual"  # manual / chat
    created_at: datetime = Field(default_factory=now)


class DerivedStrategy(SQLModel, table=True):
    id: str = Field(primary_key=True)  # user_ 开头
    base_id: str
    name: str
    description: str = ""
    params_json: str = Field(default="{}", sa_column=Column(Text))
    universe: str | None = None
    user_id: int | None = Field(default=None, index=True)  # 创建者；开启登录后只对创建者可见
    created_at: datetime = Field(default_factory=now)


_engine = None


def engine():
    global _engine
    if _engine is None:
        s = get_settings()
        if s.database_url.startswith("sqlite:///"):
            from pathlib import Path
            Path(s.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        # timeout：等锁最多 30 秒；TRUNCATE：日志文件保留、只清空，不反复创建删除。
        # Windows（以及 WSL 访问 Windows 磁盘）上刚删除的文件会短暂"删除挂起"，并发写入时
        # 默认的 DELETE 模式会偶发 "unable to open database file"
        _engine = create_engine(s.database_url, connect_args={"check_same_thread": False, "timeout": 30})
        if s.database_url.startswith("sqlite"):
            event.listen(_engine, "connect", lambda con, _: con.execute("PRAGMA journal_mode=TRUNCATE"))
        SQLModel.metadata.create_all(_engine)
        _migrate(_engine)
    return _engine


def _migrate(eng) -> None:
    """旧数据库补列（create_all 不会修改已有的表）。"""
    with eng.begin() as con:
        for table, col in (("chatsession", "user_id"), ("backtestrecord", "user_id"), ("derivedstrategy", "user_id"),
                           ("user", "class_id")):
            cols = {r[1] for r in con.exec_driver_sql(f'PRAGMA table_info("{table}")')}
            if cols and col not in cols:
                con.exec_driver_sql(f'ALTER TABLE "{table}" ADD COLUMN {col} INTEGER')
                con.exec_driver_sql(f'CREATE INDEX IF NOT EXISTS ix_{table}_{col} ON "{table}" ({col})')
        # 旧版本只有 admin / user 两种角色，user 即学生
        con.exec_driver_sql("""UPDATE "user" SET role = 'student' WHERE role = 'user'""")
        # 对话里只显示模型名，不显示接口（渠道）名称：旧消息的"接口 / 模型"改为只保留模型
        con.exec_driver_sql("""UPDATE chatmessage SET model = substr(model, instr(model, ' / ') + 3)
                               WHERE model LIKE '% / %'""")


def session() -> Iterator[Session]:
    with Session(engine()) as s:
        yield s


def get_setting(key: str, default: Any = None) -> Any:
    with Session(engine()) as s:
        row = s.get(AppSetting, key)
        return json.loads(row.value) if row else default


def set_setting(key: str, value: Any) -> None:
    with Session(engine()) as s:
        row = s.get(AppSetting, key) or AppSetting(key=key, value="")
        row.value = json.dumps(value, ensure_ascii=False)
        s.add(row)
        s.commit()


__all__ = ["LLMProvider", "AppSetting", "ClassRoom", "ChatSession", "ChatMessage", "BacktestRecord", "DerivedStrategy",
           "engine", "session", "get_setting", "set_setting", "select", "Session", "now"]
