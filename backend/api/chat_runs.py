"""对话生成放在后台任务里运行，与浏览器连接解耦。

学生在回答过程中切换页面、刷新或短暂断网，生成都不会中断，结果照常保存；
回到这个对话时，前端通过 /api/chat/sessions/{sid}/live 重新订阅，从头回放已产生的事件并继续接收。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

KEEP_SECONDS = 120  # 生成结束后保留事件的时间，供刚好在结束前后回来的页面接上

RUNS: dict[str, Run] = {}
_TASKS: set[asyncio.Task] = set()  # 持有任务引用，防止被垃圾回收


class Run:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.done = False
        self.sid: str | None = None
        self.message_id: int | None = None
        self.task: asyncio.Task | None = None
        self._changed = asyncio.Event()

    def push(self, ev: dict[str, Any]) -> None:
        self.events.append(ev)
        self._changed.set()

    def text(self) -> str:
        return "".join(e.get("text", "") for e in self.events if e.get("type") == "delta")

    async def follow(self) -> AsyncIterator[dict[str, Any]]:
        """从第一条事件开始回放，然后持续接收直到生成结束。"""
        i = 0
        while True:
            while i < len(self.events):
                yield self.events[i]
                i += 1
            if self.done:
                return
            self._changed.clear()
            await self._changed.wait()


def running(sid: str | None) -> bool:
    r = RUNS.get(sid or "")
    return bool(r and not r.done)


def start(gen: AsyncIterator[dict[str, Any]], on_stop: Callable[[Run], None]) -> Run:
    """在后台消费对话事件流。第一条 session 事件出现后按会话登记，便于重新订阅和停止。"""
    run = Run()

    async def main() -> None:
        try:
            async for ev in gen:
                if ev.get("type") == "session":
                    run.sid, run.message_id = ev["session_id"], ev.get("message_id")
                    RUNS[run.sid] = run
                run.push(ev)
        except asyncio.CancelledError:  # 学生点了停止
            on_stop(run)
            run.push({"type": "error", "message": "已停止生成"})
            run.push({"type": "done", "message_id": run.message_id, "content": ""})
        except Exception as e:  # noqa: BLE001
            run.push({"type": "error", "message": f"{type(e).__name__}: {e}"})
            run.push({"type": "done", "message_id": run.message_id, "content": ""})
        finally:
            run.done = True
            run._changed.set()
            if run.sid:
                sid = run.sid
                asyncio.get_running_loop().call_later(KEEP_SECONDS, lambda: RUNS.pop(sid, None) if RUNS.get(sid) is run else None)

    run.task = asyncio.create_task(main())
    _TASKS.add(run.task)
    run.task.add_done_callback(_TASKS.discard)
    return run


def stop(sid: str) -> bool:
    r = RUNS.get(sid)
    if not r or r.done or not r.task:
        return False
    r.task.cancel()
    return True
