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

    database_url: str = f"sqlite:///{DATA_DIR / 'app.db'}"
    results_dir: Path = DATA_DIR / "results"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # 回测在独立进程池中计算，多人同时使用时能利用多核；设为 0 则在请求线程内直接计算（测试时使用）
    backtest_workers: int = max(1, min(2, (os.cpu_count() or 2) - 1))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
