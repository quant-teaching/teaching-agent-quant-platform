"""并发对话压测（会调用真实大模型）：多个会话同时提问，统计首字时间、总耗时、工具调用、核验结果与错误。

用法（服务已启动并配置好模型，在 backend/ 下）：uv run python scripts/stress_chat.py
"""

import asyncio
import json
import time

import httpx

QS = [
    "什么是夏普比率？用一句话举例说明",
    "使用 RSI 超买超卖策略，对沪深 A 股回测 2023-01-01 至 2024-12-31，简要点评",
    "海龟交易法则适合什么行情？",
    "把动量选股和股息率轮动做等权组合，回测 2022-01-01 至 2024-12-31，简要分析分散化效果",
]


async def one(c, q):
    t0 = time.perf_counter()
    first = None
    tools = []
    fc = None
    err = None
    sid = None
    n = 0
    async with c.stream("POST", "/api/chat", json={"message": q}) as r:
        async for line in r.aiter_lines():
            if not line.startswith("data:"):
                continue
            e = json.loads(line[5:])
            n += 1
            if e["type"] == "session":
                sid = e["session_id"]
            elif e["type"] == "delta" and first is None:
                first = time.perf_counter() - t0
            elif e["type"] == "tool_end":
                tools.append(e["name"] + ("" if e["ok"] else "✗"))
            elif e["type"] == "fact_check":
                fc = f"{e['status']}({e['checked']})"
            elif e["type"] == "error":
                err = e["message"]
            elif e["type"] == "switch":
                tools.append(f"[切换→{e['to']}]")
    return q[:18], sid, first, time.perf_counter() - t0, tools, fc, err, n


async def main():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=600) as c:
        t = time.perf_counter()
        res = await asyncio.gather(*(one(c, q) for q in QS))
        print(f"{len(QS)} 个会话并发，总耗时 {time.perf_counter() - t:.1f}s")
        for q, sid, first, total, tools, fc, err, n in res:
            print(
                f"- {q:20} 会话 {sid}  首字 {first and round(first, 1)}s  总 {total:.1f}s  事件 {n}  工具 {tools}  核验 {fc}  错误 {err}"
            )
        print("会话互不串扰：", len({r[1] for r in res}) == len(QS))
        hc = await c.get("/api/health")
        print("服务健康：", hc.json())


asyncio.run(main())
