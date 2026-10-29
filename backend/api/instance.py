"""同一个数据目录只允许一个平台实例运行。

项目文件夹可能同时被 Windows 和 WSL / Linux 使用（例如放在 D 盘、WSL 通过 /mnt 访问）。两个系统之间的
SQLite 文件锁并不互通，两个实例同时写同一个 app.db 会报错甚至损坏数据库。启动时在数据库所在目录登记心跳，
发现另一个仍在运行的实例就拒绝启动。
"""

from __future__ import annotations

import json
import logging
import os
import platform
import threading
import time
from pathlib import Path

from .settings import get_settings

HEARTBEAT = 15  # 秒
STALE = 60  # 超过这么久没有心跳，视为已退出

log = logging.getLogger("uvicorn.error")
_stop = threading.Event()
_path: Path | None = None


class InstanceConflict(RuntimeError):
    pass


def _me() -> dict:
    return {"pid": os.getpid(), "host": platform.node(), "system": platform.system()}


def _lock_path() -> Path | None:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        return None
    return Path(url.removeprefix("sqlite:///")).parent / "instance.json"


def _alive(info: dict) -> bool:
    if time.time() - info.get("heartbeat", 0) > STALE:
        return False
    # 同一台机器上的同一个系统：进程已经不存在就不算冲突（Windows 上 os.kill 会结束进程，不能用来探测）
    if info.get("host") == platform.node() and info.get("system") == platform.system() and os.name == "posix":
        try:
            os.kill(int(info["pid"]), 0)
        except (OSError, ValueError, KeyError):
            return False
    return True


def _write(started: float) -> None:
    assert _path is not None
    tmp = _path.with_suffix(".tmp")
    tmp.write_text(json.dumps({**_me(), "started": started, "heartbeat": time.time()}), encoding="utf-8")
    os.replace(tmp, _path)


def acquire() -> None:
    global _path
    path = _lock_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        other = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        other = None
    me = _me()
    if other and {k: other.get(k) for k in me} != me and _alive(other):
        ago = max(0, int(time.time() - other.get("heartbeat", 0)))
        raise InstanceConflict(
            f"数据目录 {path.parent} 正被另一个平台实例使用（{other.get('system')} · {other.get('host')} · "
            f"进程 {other.get('pid')}，{ago} 秒前仍在运行）。两个实例同时写同一个数据库会出错甚至损坏数据，"
            "请先关闭那个实例再启动；如果确实要同时运行，请给这个实例设置不同的 DATABASE_URL 和 RESULTS_DIR。"
            f"如果确认那个实例已经关闭，等待 {STALE} 秒或删除 {path} 后重试。"
        )
    _path = path
    started = time.time()
    _write(started)
    _stop.clear()

    def beat() -> None:
        while not _stop.wait(HEARTBEAT):
            try:
                _write(started)
            except OSError as e:  # 心跳写失败不影响服务
                log.warning("写入实例心跳失败：%s", e)

    threading.Thread(target=beat, name="instance-heartbeat", daemon=True).start()


def release() -> None:
    global _path
    _stop.set()
    if _path is None:
        return
    try:
        info = json.loads(_path.read_text(encoding="utf-8"))
        if info.get("pid") == os.getpid() and info.get("host") == platform.node():
            _path.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass
    _path = None
