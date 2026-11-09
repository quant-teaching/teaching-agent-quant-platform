"""运行配置。优先读取环境变量，其次读取项目根目录的 .env 和公共环境文件夹里的密钥文件。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from quant.paths import DATA_DIR, ROOT_DIR

ENV_SECRETS = Path("/workspace/claude-data/环境/secrets/quant-platform.env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ENV_SECRETS, ROOT_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # 首次启动时用来初始化"模型设置"，之后以页面上的配置为准
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_provider_name: str = "默认接口"
    llm_model: str = ""
    llm_fallback_model: str = ""
    # 离线兜底：云端模型都不可用时，由规则助手解析意图、调用工具、按模板整理真实结果（不使用任何模型）
    offline_fallback: bool = True

    database_url: str = f"sqlite:///{DATA_DIR / 'app.db'}"
    results_dir: Path = DATA_DIR / "results"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # 回测在独立进程池中计算，多人同时使用时能利用多核；设为 0 则在请求线程内直接计算（测试时使用）
    backtest_workers: int = max(1, min(2, (os.cpu_count() or 2) - 1))
    # 账号登录：多人共用的服务器上开启。关闭时（本地单人使用）不需要登录
    auth_enabled: bool = False
    # 旧版本的全局注册邀请码：首次升级时变成「默认班级」的邀请码；之后学生用各班级的邀请码注册
    invite_code: str = ""
    # 教师注册码：老师凭它注册老师账号；为空时不开放老师注册（管理员也可在设置页面修改）
    teacher_invite_code: str = ""
    # 管理员账号：开启登录时，每次启动按这里的用户名和密码创建或重置管理员；只有管理员能修改模型设置。
    # 不开启登录时，设置了 ADMIN_PASSWORD 则修改模型设置需要先在页面上输入它解锁
    admin_username: str = "admin"
    admin_password: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
