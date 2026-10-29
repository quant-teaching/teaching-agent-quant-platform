"""压测：并发回测请求，同时探测健康接口延迟，统计吞吐、延迟分位数与错误。

用法（服务已启动，在 backend/ 下）：uv run python scripts/stress_backtest.py [请求数=44] [并发=8]
压测产生的回测记录会在结束后自动删除。
"""

import asyncio
import random
import statistics
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
STRATS = [
    "dual_ma_stock",
    "momentum_stock",
    "reversal_stock",
    "multi_factor_stock",
    "industry_rotation",
    "bollinger_stock",
    "rsi_stock",
    "grid_stock",
    "macd_stock",
    "kdj_stock",
    "risk_parity_stock",
    "dividend_rotation",
    "turtle_futures",
    "atr_channel_futures",
    "calendar_spread_futures",
    "trend_cta_futures",
    "mean_reversion_futures",
    "bollinger_futures",
    "volatility_breakout_futures",
    "ma_channel_futures",
    "grid_futures",
    "dual_ma_futures",
]
PERIODS = [
    ("2021-01-01", "2024-12-31"),
    ("2022-01-01", "2025-12-31"),
    ("2023-01-01", "2025-06-30"),
    ("2020-06-01", "2026-10-28"),
]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


async def main(total: int, conc: int):
    sem = asyncio.Semaphore(conc)
    lat, errs, ids = [], [], []
    health = []
    done = asyncio.Event()
    async with httpx.AsyncClient(base_url=BASE, timeout=300) as c:

        async def one(i):
            sid = STRATS[i % len(STRATS)]
            s, e = random.choice(PERIODS)
            async with sem:
                t = time.perf_counter()
                try:
                    r = await c.post("/api/backtests", json={"strategy": sid, "config": {"start": s, "end": e}})
                    if r.status_code != 200:
                        errs.append((sid, r.status_code, r.text[:120]))
                    else:
                        ids.append(r.json()["id"])
                except Exception as ex:
                    errs.append((sid, type(ex).__name__, str(ex)[:120]))
                lat.append(time.perf_counter() - t)

        async def probe():
            while not done.is_set():
                t = time.perf_counter()
                try:
                    await c.get("/api/health")
                    health.append(time.perf_counter() - t)
                except Exception:
                    health.append(99)
                await asyncio.sleep(0.5)

        t0 = time.perf_counter()
        pr = asyncio.create_task(probe())
        await asyncio.gather(*(one(i) for i in range(total)))
        done.set()
        await pr
        wall = time.perf_counter() - t0
        # 并发读取已完成的结果（报告页的典型负载）
        t1 = time.perf_counter()
        rs = await asyncio.gather(*(c.get(f"/api/backtests/{i}") for i in ids))
        read_wall = time.perf_counter() - t1
        read_ok = sum(r.status_code == 200 for r in rs)
        for i in ids:
            await c.delete(f"/api/backtests/{i}")
    print(
        f"回测请求 {total} 个，并发 {conc}：成功 {len(ids)}，失败 {len(errs)}，总耗时 {wall:.1f}s，吞吐 {total / wall:.2f} 个/秒"
    )
    print(f"  单次延迟 中位数 {statistics.median(lat):.2f}s  P90 {pct(lat, 0.9):.2f}s  最大 {max(lat):.2f}s")
    print(
        f"  压测期间健康检查 {len(health)} 次：中位数 {statistics.median(health) * 1000:.0f}ms  最大 {max(health) * 1000:.0f}ms"
    )
    print(f"  并发读取 {len(ids)} 个结果：成功 {read_ok}，耗时 {read_wall:.2f}s")
    for e in errs[:5]:
        print("  错误:", e)


asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 44, int(sys.argv[2]) if len(sys.argv) > 2 else 8))
