"""下载教学用行情快照到 data/market/。

用法（在 backend/ 下）：
    uv run python scripts/download_data.py              # 下载全部，截止今天
    uv run python scripts/download_data.py --end 2026-10-28 --only stocks futures

每个标的的原始结果缓存在 data/cache/raw/，中断后重跑会跳过已下载的部分；加 --refresh 强制重下。
下载完成后自动构建期货主力连续合约，并写入 manifest.json 记录快照范围。
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

import akshare as ak
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.data.catalog import BENCHMARKS, FUTURES, STOCK_POOL  # noqa: E402
from quant.data.futures_continuous import build_continuous  # noqa: E402
from quant.paths import CACHE_DIR, MARKET_DIR  # noqa: E402

STOCK_START = "2016-01-01"
FUTURES_START = "2019-01-01"
# 新浪只保留 2020 年及以后到期的合约（最早 2019 年 1 月上市）。2019 年里这些合约还不是真正的主力，
# 到 2020 年初各品种的真实主力都已落在可得合约中，所以连续合约从这里开始
FUTURES_VALID_FROM = "2020-01-01"
FUTURES_YEARS = range(2020, 2028)

RAW_DIR = CACHE_DIR / "raw"
_refresh = False


class FetchTimeout(Exception):
    pass


def _on_alarm(signum, frame):
    raise FetchTimeout("请求超过 60 秒")


signal.signal(signal.SIGALRM, _on_alarm)


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def cached(name: str, fetch: Callable[[], pd.DataFrame], retries: int = 3) -> pd.DataFrame | None:
    """带缓存和重试的下载。返回 None 表示该标的不存在或多次失败。"""
    path = RAW_DIR / f"{name}.parquet"
    missing = RAW_DIR / f"{name}.missing"
    if not _refresh:
        if path.exists():
            return pd.read_parquet(path)
        if missing.exists():
            return None
    for attempt in range(1, retries + 1):
        try:
            signal.alarm(60)  # akshare 的请求没有超时，用闹钟信号兜底
            try:
                df = fetch()
            finally:
                signal.alarm(0)
            time.sleep(0.25)
            if df is None or df.empty:
                missing.touch()
                return None
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path, index=False)
            return df
        except ValueError as e:
            # 新浪对不存在的合约返回空表，akshare 在改列名时抛 Length mismatch
            if "Length mismatch" in str(e):
                missing.touch()
                return None
            err = e
        except Exception as e:  # 网络错误
            err = e
        log(f"  {name} 第 {attempt} 次失败：{type(err).__name__} {str(err)[:80]}")
        time.sleep(2 * attempt)
    return None


def _ymd(s: str) -> str:
    return s.replace("-", "")


def download_stocks(end: str) -> None:
    frames = []
    for i, s in enumerate(STOCK_POOL, 1):
        log(f"股票 {i}/{len(STOCK_POOL)} {s.code} {s.name}")
        qfq = cached(
            f"stock_qfq_{s.code}",
            lambda s=s: ak.stock_zh_a_daily(
                symbol=s.sina_symbol, start_date=_ymd(STOCK_START), end_date=_ymd(end), adjust="qfq"
            ),
        )
        raw = cached(
            f"stock_raw_{s.code}",
            lambda s=s: ak.stock_zh_a_daily(
                symbol=s.sina_symbol, start_date=_ymd(STOCK_START), end_date=_ymd(end), adjust=""
            ),
        )
        if qfq is None or raw is None:
            log(f"  !! {s.code} 下载失败，跳过")
            continue
        df = qfq[["date", "open", "high", "low", "close", "volume", "amount", "turnover"]].copy()
        df = df.merge(
            raw[["date", "close"]].rename(columns={"close": "close_raw"}), on="date", how="left"
        )
        df.insert(1, "symbol", s.code)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    out = out[out["date"] <= end].sort_values(["symbol", "date"])
    write(out, "stock_daily")

    divs = []
    for s in STOCK_POOL:
        d = cached(
            f"dividend_{s.code}",
            lambda s=s: ak.stock_history_dividend_detail(symbol=s.code, indicator="分红"),
        )
        if d is None:
            continue
        d = d[(d["进度"] == "实施") & d["除权除息日"].notna()]
        divs.append(
            pd.DataFrame(
                {
                    "symbol": s.code,
                    "ex_date": pd.to_datetime(d["除权除息日"]),
                    "cash_per_share": d["派息"].astype(float) / 10,  # 原始单位：每 10 股派息（元）
                }
            )
        )
    write(pd.concat(divs, ignore_index=True).sort_values(["symbol", "ex_date"]), "dividends")


def download_indexes(end: str) -> None:
    frames = []
    for idx in BENCHMARKS:
        log(f"指数 {idx.code} {idx.name}")
        df = cached(f"index_{idx.code}", lambda i=idx: ak.stock_zh_index_daily(symbol=i.sina_symbol))
        df = df[["date", "open", "high", "low", "close", "volume"]].copy()
        df.insert(1, "symbol", idx.code)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    write(out[(out["date"] >= STOCK_START) & (out["date"] <= end)], "index_daily")


def download_industries(end: str) -> None:
    info = cached("sw_first_info", ak.sw_index_first_info)
    frames = []
    for i, row in enumerate(info.itertuples(index=False), 1):
        code, name = row[0].split(".")[0], row[1]
        log(f"申万行业 {i}/{len(info)} {code} {name}")
        df = cached(f"sw_{code}", lambda c=code: ak.index_hist_sw(symbol=c, period="day"))
        if df is None:
            continue
        df = df.rename(
            columns={"日期": "date", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close",
                     "成交量": "volume", "成交额": "amount"}
        )[["date", "open", "high", "low", "close", "volume", "amount"]]
        df.insert(1, "symbol", code)
        df.insert(2, "name", name)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    write(out[(out["date"] >= STOCK_START) & (out["date"] <= end)], "industry_daily")


def download_futures(end: str) -> None:
    frames = []
    for spec in FUTURES:
        contracts = [f"{spec.code}{y % 100:02d}{m:02d}" for y in FUTURES_YEARS for m in spec.months]
        log(f"期货 {spec.code} {spec.name}：尝试 {len(contracts)} 个合约")
        got = 0
        for c in contracts:
            df = cached(f"fut_{c}", lambda c=c: ak.futures_zh_daily_sina(symbol=c))
            if df is None:
                continue
            df = df[["date", "open", "high", "low", "close", "volume", "hold", "settle"]].copy()
            df.insert(1, "product", spec.code)
            df.insert(2, "contract", c)
            frames.append(df)
            got += 1
        log(f"  {spec.code} 获得 {got} 个合约")
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    out = out[(out["date"] >= FUTURES_START) & (out["date"] <= end)]
    write(out.sort_values(["product", "contract", "date"]), "futures_contracts")
    log("构建主力连续合约")
    cont = build_continuous(out)
    write(cont[cont["date"] >= FUTURES_VALID_FROM], "futures_continuous")


def write(df: pd.DataFrame, name: str) -> None:
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(MARKET_DIR / f"{name}.parquet", index=False, compression="zstd")
    log(f"写入 {name}.parquet：{len(df)} 行")


def write_manifest(end: str) -> None:
    manifest = {"generated_at": datetime.now().isoformat(timespec="seconds"), "end": end, "datasets": {}}
    for p in sorted(MARKET_DIR.glob("*.parquet")):
        df = pd.read_parquet(p)
        dcol = "date" if "date" in df.columns else "ex_date"
        manifest["datasets"][p.stem] = {
            "rows": len(df),
            "start": str(df[dcol].min().date()),
            "end": str(df[dcol].max().date()),
        }
    (MARKET_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    log("写入 manifest.json")


TASKS = {
    "stocks": download_stocks,
    "indexes": download_indexes,
    "industries": download_industries,
    "futures": download_futures,
}


def main() -> None:
    global _refresh
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--end", default=str(date.today()), help="快照截止日期 YYYY-MM-DD")
    p.add_argument("--only", nargs="*", choices=list(TASKS), help="只下载指定数据集")
    p.add_argument("--refresh", action="store_true", help="忽略缓存重新下载")
    args = p.parse_args()
    _refresh = args.refresh
    for name in args.only or TASKS:
        TASKS[name](args.end)
    write_manifest(args.end)


if __name__ == "__main__":
    main()
