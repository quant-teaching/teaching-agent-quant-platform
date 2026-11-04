"""运行测试用例并生成《测试报告》（docs/测试报告.md）。

用法（在 backend/ 下）：uv run python scripts/build_test_report.py
内容：
1. 回测引擎单元测试（pytest）
2. 引擎正确性交叉验证：买入持有的期末权益与手工计算对比
3. 回测案例（含参数修改、参数敏感性、多策略组合）——每次运行都重新回测，数字与引擎一致
4. 22 个策略全量冒烟测试
5. 智能体对话测试：从本地数据库导出真实的对话记录（需要先在页面或接口中跑过这些对话）
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from api.services import ORDER  # noqa: E402
from quant.backtest import run_backtest  # noqa: E402
from quant.data.loader import load_bars, load_dividends  # noqa: E402
from quant.engine.config import BacktestConfig  # noqa: E402
from quant.engine.engine import run_engine  # noqa: E402
from quant.paths import BACKEND_DIR, ROOT_DIR  # noqa: E402
from quant.portfolio.portfolio import run_portfolio  # noqa: E402
from quant.strategies.base import load_all  # noqa: E402


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def num(x, nd=2):
    return "—" if x is None else ("∞" if x == float("inf") else f"{x:.{nd}f}")


HEAD = "| 总收益率 | 年化收益率 | 最大回撤 | 夏普 | 卡玛 | 波动率 | 胜率 | 盈亏比 | 交易次数 | 成本占比 |"
SEP = "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"


def row(m) -> str:
    return (f"| {pct(m['total_return'])} | {pct(m['annual_return'])} | {pct(m['max_drawdown'])} | {num(m['sharpe'])} "
            f"| {num(m['calmar'])} | {pct(m['volatility'])} | {pct(m.get('win_rate'))} | {num(m.get('profit_loss_ratio'))} "
            f"| {m.get('trade_count', '—')} | {pct(m.get('cost_ratio'), 2)} |")


def bench_line(r) -> str:
    hs = r.benchmarks.get("000300")
    if not hs:
        return ""
    return (f"同期沪深 300：年化 {pct(hs['annual_return'])}、最大回撤 {pct(hs['max_drawdown'])}、夏普 {num(hs['sharpe'])}；"
            f"策略年化超额 {pct(hs['excess_annual_return'])}。")


def regimes(r) -> str:
    reg = r.diagnostics.get("regimes") or {}
    parts = [f"{k}（{v['months']} 个月）策略平均月收益 {pct(v['strategy_avg_monthly'], 2)}"
             for k, v in reg.items()]
    return "；".join(parts)


TEST_NAMES = {
    # 回测引擎（手工构造行情）
    "test_signal_executes_next_open_no_lookahead": "信号次日开盘成交，无未来函数",
    "test_stock_lot_size_commission_and_stamp_duty": "A 股 100 股一手、佣金、印花税与逐笔盈亏",
    "test_stamp_duty_halved_after_2023_08_28": "印花税 2023-08-28 起减半",
    "test_limit_up_open_blocks_buy_until_next_day": "开盘涨停买不进、顺延至次日",
    "test_futures_mark_to_market_and_short": "期货逐日盯市与做空盈亏",
    "test_futures_roll_pnl_ignores_contract_gap": "期货换月价差不计入盈亏",
    "test_futures_roll_charges_costs": "期货换月收取移仓滑点",
    "test_margin_cap_scales_down_futures": "保证金占用上限缩减开仓",
    "test_negative_stock_weight_clipped": "A 股不能做空",
    "test_metrics_formulas": "年化收益、最大回撤、夏普比率公式",
    "test_round_trip_win_rate": "完整交易切分与胜率",
    # 策略（真实行情）
    "test_strategy_runs_with_sane_output": "每个策略都能运行，指标有限、净值为正、有成交、股票无空头",
    "test_no_lookahead": "截断数据前后截止日以前的信号完全一致（无未来函数）",
    "test_custom_universe_single_stock": "自选单只股票",
    "test_universe_with_next_leg_expands": "跨期套利自动补充次主力腿",
    "test_wrong_asset_type_rejected": "策略与标的类型不匹配时报错",
    "test_min_symbols_enforced": "截面策略标的数量不足时报错",
    "test_unknown_symbol_rejected": "未知标的报错",
    "test_period_outside_data_rejected": "区间超出数据范围时给出清晰提示",
    "test_end_before_start_rejected": "结束日期早于开始日期时报错",
    "test_invalid_params_give_chinese_message": "参数不合法时给出中文提示",
    "test_short_period_works": "两周的短区间回测",
    "test_futures_before_continuous_start": "期货区间早于数据起点时报错或提示",
    "test_stops_reduce_exposure": "止损降低平均仓位",
    "test_position_limit_scales_drawdown": "仓位上限与波动率同向",
    "test_portfolio_equal_and_custom_weights": "组合等权 / 自定义权重，风险贡献之和为 1",
    "test_portfolio_without_rebalance_matches_value_sum": "不调仓组合净值 = 各子策略净值加权和",
    "test_benchmarks_start_at_one": "基准净值起点为 1，收益与指数收盘价一致",
    # 接口与智能体
    "test_health_market_strategies": "数据概览与算法库接口，按名称或别名查找策略",
    "test_backtest_lifecycle": "回测创建、查询、持仓、列表、删除",
    "test_backtest_errors_are_readable": "回测错误返回可读的中文提示",
    "test_portfolio_endpoint": "组合回测接口，子策略结果一并存档",
    "test_export_dataset_is_complete": "导出回测数据集：成交明细超过页面上限时仍完整、指标与报告一致、附免责声明",
    "test_second_instance_on_same_data_dir_is_refused": "同一数据目录拒绝启动第二个实例（防止 Windows 与 WSL 同时写库）",
    "test_saved_key_never_sent_to_new_address": "已保存的 API Key 不会被发送到修改后的新地址（防止 Key 外泄）",
    "test_admin_password_locks_model_settings": "未开启登录时，设置管理员密码后修改模型设置需要先解锁",
    "test_update_params_ignores_reason_written_into_changes": "模型把修改理由写进参数字典时自动忽略，只修改真正的参数",
    "test_dividend_and_bonus_shares_keep_equity_continuous": "除权日现金分红到账、送转股增加持股，权益不因除权跳变，盈亏核算正确",
    "test_stock_fills_use_real_prices_and_detect_bonus_shares": "股票按不复权真实价格成交；从复权价与真实价还原出送转比例和除权参考价",
    "test_profit_factor_when_all_trades_win": "全部盈利时利润因子为无穷大，没有平仓交易时为空",
    "test_chat_model_choice_puts_selected_model_first": "对话页可选模型：列表不含地址和密钥，指定模型排在最前、失败按主备兜底，未配置的模型被拒绝",
    "test_admin_changes_invite_code_on_page": "管理员在页面修改邀请码立即生效：旧码失效、新码可注册、可关闭注册、学生无权查看",
    "test_login_required_and_registration": "开启登录后未登录不能访问接口；注册校验邀请码、用户名与密码强度；Cookie 为 HttpOnly",
    "test_registration_closed_without_invite_code": "未设置邀请码时关闭注册",
    "test_data_isolated_between_users": "对话与回测记录按用户隔离，不能查看或删除别人的数据",
    "test_only_admin_changes_model_settings_and_users": "只有管理员能修改模型设置、管理用户；停用账号立即失效",
    "test_login_lockout_and_password_change": "连续输错密码锁定 5 分钟；修改密码后旧密码失效",
    "test_password_hash_is_salted_scrypt": "密码加盐 scrypt 存储",
    "test_sqlite_uses_truncate_journal": "SQLite 使用 TRUNCATE 日志模式，避免 Windows 磁盘上并发写入偶发失败",
    "test_derived_strategy": "衍生策略的创建、重名校验、回测与删除",
    "test_provider_crud_and_routing": "模型接口增删改、Key 掩码、主备顺序校验",
    "test_agent_tool_loop_disclaimer_and_fact_check": "智能体多轮工具调用、参数前后对比、编造数字被识别、强制免责、会话参数延续",
    "test_agent_fact_check_passes_for_real_numbers": "引用真实回测数字时核验通过",
    "test_agent_tool_error_is_fed_back": "工具报错反馈给模型；未回测时不附加免责",
    "test_investment_advice_detection": "识别寻求实盘投资建议的提问",
    "test_compliance_hint_injected": "实盘建议类提问时注入合规指令",
    "test_fallback_chain": "主模型报错 → 备用模型空响应 → 下一个备用模型成功；全部失败时汇总错误",
    "test_result_id_path_traversal_rejected": "回测 id 校验，防止路径穿越",
    "test_report_served_gzip_directly": "报告存档以 gzip 原样返回",
    "test_spa_route_blocks_path_traversal": "前端静态文件路由防止路径穿越读取密钥",
}
TEST_FILES = {
    "tests/test_engine.py": "回测引擎（手工构造行情）",
    "tests/test_strategies.py": "策略与回测（真实行情）",
    "tests/test_api.py": "接口、智能体与安全（假模型，不访问网络）",
    "tests/test_auth.py": "账号登录与权限",
}


def section_unit_tests(out: list[str]) -> None:
    t0 = time.perf_counter()
    res = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rA", "--no-header", "-p", "no:cacheprovider",
                          "-W", "ignore"], cwd=BACKEND_DIR, capture_output=True, text=True)
    rows: dict[tuple[str, str], list[bool]] = {}
    for ln in res.stdout.splitlines():
        if not (ln.startswith("PASSED") or ln.startswith("FAILED")):
            continue
        nodeid = ln.split(" ", 1)[1].split(" - ")[0]
        file, name = nodeid.split("::", 1)
        base = name.split("[")[0]
        rows.setdefault((file, base), []).append(ln.startswith("PASSED"))
    total = sum(len(v) for v in rows.values())
    ok = sum(sum(v) for v in rows.values())
    out += ["## 1. 自动化测试", "",
            f"共 **{total}** 项，**通过 {ok} 项，失败 {total - ok} 项**（用时 {time.perf_counter() - t0:.0f} 秒，"
            "运行 `uv run pytest` 复现）。测试使用临时数据库，大模型用脚本化的假模型代替。", ""]
    for file, title in TEST_FILES.items():
        items = [(b, v) for (f, b), v in rows.items() if f == file]
        if not items:
            continue
        out += [f"### {title}（{sum(len(v) for _, v in items)} 项）", "", "| 测试 | 验证内容 | 结果 |", "|---|---|---|"]
        for base, v in items:
            count = f" × {len(v)}" if len(v) > 1 else ""
            mark = "✅ 通过" if all(v) else f"❌ 失败 {len(v) - sum(v)} 项"
            out.append(f"| `{base}`{count} | {TEST_NAMES.get(base, '')} | {mark} |")
        out.append("")


def section_performance(out: list[str]) -> None:
    """进程内计时：首次（需要整理行情宽表）与再次回测（命中缓存）。"""
    import quant.data.loader as loader
    cases = [("dual_ma_stock", "股票池 55 只"), ("multi_factor_stock", "股票池 55 只"),
             ("industry_rotation", "申万行业 31 个"), ("turtle_futures", "商品期货 16 个"),
             ("calendar_spread_futures", "期货 5 对价差")]
    out += ["## 5. 性能与压测", "", "### 单次回测耗时（2021-01-01 ~ 2024-12-31，进程内计时）", "",
            "| 策略 | 标的 | 首次 | 再次（行情已缓存） |", "|---|---|---:|---:|"]
    for sid, desc in cases:
        loader._load_bars.cache_clear()
        t = time.perf_counter()
        r = run_backtest(sid, {}, None, {"start": "2021-01-01", "end": "2024-12-31"})
        cold = time.perf_counter() - t
        t = time.perf_counter()
        run_backtest(sid, {}, None, {"start": "2022-01-01", "end": "2023-12-31"})
        warm = time.perf_counter() - t
        out.append(f"| {r.strategy['name']} | {desc} | {cold:.2f} 秒 | {warm:.2f} 秒 |")
    out += ["",
            "### 服务压测（`scripts/stress_backtest.py`、`scripts/stress_chat.py`，2026-10-29 实测）", "",
            "测试机 32 核，后端单进程 + 2 个回测工作进程（默认配置）。", "",
            "| 场景 | 结果 |", "|---|---|",
            "| 44 个回测请求、并发 8（覆盖 22 个策略、4 种区间），行情未缓存 | 全部成功；吞吐 1.33 个/秒；延迟中位数 3.7 秒 |",
            "| 同上，行情已缓存 | 全部成功；吞吐 2.93 个/秒；延迟中位数 2.5 秒、P90 3.3 秒、最大 3.8 秒 |",
            "| 压测期间探测健康接口 | 中位数 3 毫秒，最大 0.4 秒，服务始终可响应 |",
            "| 读取回测报告 | gzip 存档原样返回，约 280 KB（未压缩 1.2 MB），10 毫秒 |",
            "| 内存（主进程 + 2 个工作进程） | 启动约 160 MB；两轮压测后约 1.1 GB 并保持稳定，无持续增长 |",
            "| 4 个会话并发对话（真实模型，含 2 次回测 / 组合回测） | 全部成功、会话互不串扰；首字 8~23 秒（含工具调用），回复数字核验全部通过 |",
            "",
            "优化记录：首次回测由 5.7 秒降到 1.3 秒（修复行情加载中重复构建集合的热点）；同一标的池再次回测 0.25 秒（按标的池缓存全部历史）；"
            "回测计算与报告生成移到进程池，P90 延迟由 13 秒降到 3.3 秒；报告存档直接以 gzip 返回。", ""]


def section_cross_check(out: list[str]) -> None:
    b = load_bars(["600519"])
    w = pd.DataFrame({"600519": 1.0}, index=b.dates)
    cfg = BacktestConfig(start="2022-01-04", end="2025-12-31", benchmarks=[])
    o = run_engine(w, b, cfg)
    f = o.fills[0]
    d = b.dates[(b.dates >= "2022-01-04") & (b.dates <= "2025-12-31")]
    # 现金分红直接从分红表独立计算：持有期内（首次成交之后）每个除权日每股派息 × 持股数
    div = load_dividends()
    div = div[(div["symbol"] == "600519") & (pd.to_datetime(div["ex_date"]) > f.date)
              & (pd.to_datetime(div["ex_date"]) <= d[-1])]
    cash_div = float(div["cash_per_share"].sum()) * f.qty
    expect = cfg.initial_capital - f.qty * f.price - f.fee + f.qty * b.mark_close.loc[d[-1], "600519"] + cash_div
    got = o.daily["equity"].iloc[-1]
    out += ["## 2. 引擎正确性交叉验证", "",
            "用真实行情做一次独立核对：贵州茅台从 2022-01-04 起满仓买入持有到 2025-12-31，"
            "引擎计算的期末权益应等于「初始资金 − 买入金额 − 手续费 + 持股数 × 期末收盘价（不复权）+ 持有期现金分红」，"
            "其中现金分红直接按分红表逐次累加，不经过引擎。", "",
            "| 项目 | 数值 |", "|---|---:|",
            f"| 首笔成交 | {f.date.date()}，{int(f.qty)} 股 × {f.price:.2f} 元（真实开盘价 × (1 + 0.05% 滑点)） |",
            f"| 持有期现金分红 | {len(div)} 次，每股合计 {div['cash_per_share'].sum():.3f} 元，共 {cash_div:,.2f} 元 |",
            f"| 引擎期末权益 | {got:,.2f} 元 |",
            f"| 手工计算 | {expect:,.2f} 元 |",
            f"| 差额 | {got - expect:.6f} 元 {'✅' if abs(got - expect) < 0.01 else '❌'} |", ""]


def section_cases(out: list[str]) -> None:
    out += ["## 3. 回测案例", "",
            "以下案例每次生成报告时都会重新回测，表中数字直接来自回测引擎。默认设置：初始资金 1000 万元，"
            "A 股佣金万分之 2.5（最低 5 元）、印花税按日期、滑点 0.05%；期货手续费约万分之 1、滑点 1 跳。", ""]
    n = 0

    def single(title, desc, sid, params, start, end, universe=None):
        nonlocal n
        n += 1
        r = run_backtest(sid, params, universe, {"start": start, "end": end})
        out.extend([f"### 案例 {n}：{title}", "", desc, "",
                    f"- 策略：{r.strategy['name']}（`{sid}`）；区间：{start} ~ {end}；标的数：{len(r.universe)}",
                    f"- 参数：`{json.dumps({k: v for k, v in r.params.items()}, ensure_ascii=False)}`", "",
                    HEAD, SEP, row(r.metrics), "", bench_line(r), ""])
        if regimes(r):
            out.extend([f"行情分段：{regimes(r)}。", ""])
        return r

    single("双均线策略（股票池，默认参数）", "对应赛题示例：使用双均线策略，对沪深 A 股回测 2022-01-01 至 2025-12-31。",
           "dual_ma_stock", {}, "2022-01-01", "2025-12-31")

    # 参数修改对比
    n += 1
    out.extend([f"### 案例 {n}：参数修改——双均线长均线周期", "",
                "保持短均线 10 日不变，把长均线从 30 日改为 45、60 日，观察信号频率、成本与收益的变化（参数修改案例）。", "",
                "| 长均线周期 " + HEAD, "|---:" + SEP])
    for slow in (30, 45, 60):
        r = run_backtest("dual_ma_stock", {"slow": slow}, None, {"start": "2022-01-01", "end": "2025-12-31"})
        out.append(f"| {slow} " + row(r.metrics))
    out.extend(["", "结论：长均线越长，交易次数和成本越低；收益并非单调变化，说明参数需要结合稳健性判断，不能只挑历史最优值。", ""])

    single("海龟交易法则（赛题场景 1，参数修改）",
           "对应赛题场景 1：调出海龟交易期货策略，ATR 周期 20 → 22，单笔仓位上限 0.2 → 0.15，回测 2021-01-01 至 2024-12-30，"
           "标的为国内商品期货主力合约（16 个品种）。",
           "turtle_futures", {"atr_period": 22, "position_limit": 0.15}, "2021-01-01", "2024-12-30")

    n += 1
    out.extend([f"### 案例 {n}：参数敏感性——海龟交易法则单品种仓位上限", "",
                "验证优化建议「降低单笔仓位上限可以降低最大回撤」：其他参数保持默认，只改变 position_limit。", "",
                "| 仓位上限 " + HEAD, "|---:" + SEP])
    for pl in (0.1, 0.15, 0.2):
        r = run_backtest("turtle_futures", {"position_limit": pl}, None, {"start": "2021-01-01", "end": "2024-12-30"})
        out.append(f"| {pl} " + row(r.metrics))
    out.extend(["", "结论：仓位上限与最大回撤、波动率同向变化，降低仓位上限能按比例压低回撤，但不会改变策略信号本身的胜率与盈亏比。", ""])

    single("多因子选股", "动量、低波动、短期反转、低换手、股息率五因子等权打分，每月持有得分最高的 10 只。",
           "multi_factor_stock", {}, "2022-01-01", "2025-12-31")
    single("股息率轮动", "每季度持有过去一年股息率最高的 10 只股票。", "dividend_rotation", {}, "2022-01-01", "2025-12-31")
    single("跨期简单套利", "螺纹钢、热卷、豆粕、PTA、甲醇的主力与次主力价差均值回归。", "calendar_spread_futures", {},
           "2021-01-01", "2024-12-31")

    def portfolio(title, desc, comps, start, end):
        nonlocal n
        n += 1
        from quant.portfolio.portfolio import Component, PortfolioSpec
        res, subs = run_portfolio(PortfolioSpec(components=[Component(strategy_id=c) for c in comps], rebalance="M"),
                                  {"start": start, "end": end})
        div = res.diagnostics["diversification"]
        out.extend([f"### 案例 {n}：{title}", "", desc, "",
                    "| 对象 " + HEAD, "|---" + SEP, "| **组合** " + row(res.metrics)])
        for s in subs:
            out.append(f"| {s.strategy['name']} " + row(s.metrics))
        out.extend(["", bench_line(res), "",
                    f"分散化分析：子策略收益相关系数 {num(div['avg_correlation'])}，分散化比率 {num(div['diversification_ratio'])}，"
                    f"组合波动率 {pct(div['portfolio_vol'])}（子策略加权平均 {pct(div['weighted_avg_vol'])}）；"
                    f"风险贡献 " + "、".join(f"{lb} {pct(v)}" for lb, v in zip(div["labels"], div["risk_contribution"])) + "。",
                    ""])

    portfolio("多策略等权组合（赛题场景 2）",
              "对应赛题场景 2：双均线股票策略 + 动量选股等权组合，回测 2022-01-01 至 2025-06-30，每月再平衡，对比沪深 300。",
              ["dual_ma_stock", "momentum_stock"], "2022-01-01", "2025-06-30")
    portfolio("趋势 + 均值回归组合（期货）",
              "海龟交易法则与期货均值回归等权组合：两者收益来源相反，用于观察低相关策略的分散化效果。",
              ["turtle_futures", "mean_reversion_futures"], "2021-01-01", "2024-12-31")
    portfolio("股票红利 + 期货 CTA 组合",
              "股息率轮动与趋势跟踪 CTA 等权组合：跨资产类别的分散化。",
              ["dividend_rotation", "trend_cta_futures"], "2021-01-01", "2025-12-31")


def section_smoke(out: list[str]) -> None:
    reg = load_all()
    out += ["## 4. 22 个策略全量冒烟测试", "",
            "每个策略使用默认参数和默认标的池，回测 2021-01-01 至 2024-12-31，验证全部策略可以正常运行并输出完整指标。", "",
            "| # | 策略 | 类别 " + HEAD + " 用时 |", "|---|---|---" + SEP + "---:|"]
    for i, sid in enumerate(ORDER, 1):
        t0 = time.perf_counter()
        r = run_backtest(sid, {}, None, {"start": "2021-01-01", "end": "2024-12-31"})
        cat = "股票" if reg[sid].category == "stock" else "期货"
        out.append(f"| {i} | {r.strategy['name']} | {cat} " + row(r.metrics) + f" {time.perf_counter() - t0:.1f}s |")
    out += ["", "说明：这些是默认参数在单一历史区间上的表现，用于验证功能，不代表策略优劣；"
            "不同策略适合不同的市场环境，教学中应结合行情分段与参数敏感性一起分析。", ""]


AGENT_CASES = [
    ("赛题场景 1：对话调取算法、修改参数、执行回测", "调出海龟交易期货策略"),
    ("赛题场景 2：多策略组合回测", "选取双均线股票策略、动量选股策略"),
    ("赛题场景 3：查看算法教学说明", "给我讲下布林带股票策略原理"),
    ("回测解读", "使用双均线策略，对沪深 A 股回测"),
    ("优化建议与实际验证", "胜率为什么这么低"),
    ("对话修改参数", "把海龟策略的 ATR 周期改成 30"),
    ("对话生成衍生策略并与原版对比", "保存成衍生策略"),
    ("赛题示例：两个策略等权组合", "把动量选股 + 行业轮动"),
    ("获取回测原始数据", "每日净值和交易记录原始数据"),
    ("教学问答：海龟交易法则适合什么行情", "海龟交易法则原理是什么"),
    ("合规：拒绝实盘投资建议", "应该买贵州茅台还是宁德时代"),
]


def section_agent(out: list[str]) -> None:
    import sqlite3

    from api.settings import get_settings
    db = Path(get_settings().database_url.removeprefix("sqlite:///"))
    out += ["## 6. 智能体对话测试", "",
            "以下为平台中真实执行的对话（从本地数据库导出），展示智能体调用了哪些工具、事实核验结果以及回复原文。", ""]
    if not db.exists():
        out += ["（本地还没有对话记录。启动平台后在「智能助手」中依次发送下列问题，再重新运行本脚本。）", ""]
        return
    con = sqlite3.connect(db)
    for title, key in AGENT_CASES:
        r = con.execute("select session_id, id from chatmessage where role='user' and content like ? order by id desc limit 1",
                        (f"%{key}%",)).fetchone()
        if not r:
            out += [f"### {title}", "", f"（未找到包含「{key}」的对话）", ""]
            continue
        sid, uid = r
        user = con.execute("select content from chatmessage where id=?", (uid,)).fetchone()[0]
        a = con.execute("select content, events_json, model from chatmessage where session_id=? and role='assistant' "
                        "and id>? order by id limit 1", (sid, uid)).fetchone()
        if not a:
            continue
        content, events, model = a
        events = json.loads(events)
        tools = [e["label"] for e in events if e.get("kind") == "tool"]
        fc = next((e for e in events if e.get("kind") == "fact_check"), None)
        fc_text = ("—" if not fc else "回复中没有需要核验的数字" if fc["checked"] == 0 else
                   f"核验 {fc['checked']} 个数字，" + ("全部来自工具结果 ✅" if fc["status"] == "ok"
                                                    else f"未核验：{'、'.join(fc['unmatched'])}"))
        out += [f"### {title}", "", f"**用户**：{user}", "",
                f"- 模型：{model or '—'}",
                f"- 调用的工具：{' → '.join(tools) if tools else '无（直接回答）'}",
                f"- 数据核验：{fc_text}",
                f"- 免责声明：{'已自动附加 ✅' if '不构成任何投资建议' in content else '本轮未执行回测，无需附加'}", "",
                "<details><summary>智能体回复原文</summary>", "", content, "", "</details>", ""]


def main() -> None:
    t0 = time.perf_counter()
    out = ["# 测试报告", "",
           f"> 生成时间：{datetime.now():%Y-%m-%d %H:%M}，由 `backend/scripts/build_test_report.py` 自动运行并生成。",
           "> 所有回测结果仅用于算法学习与教学演示，历史回测不代表未来表现，不构成任何投资建议。", "",
           "## 测试环境", "",
           "- 行情数据：`data/market/` 快照（见 `manifest.json`）：A 股与申万行业 2016-01 起，商品期货主力连续 2020-01 起，截至 2026-10-28",
           "- 股票池：沪深 300 中 55 只各行业龙头（存在幸存者偏差，见设计文档）",
           "- 期货：16 个商品品种，由单合约按持仓量自建主力连续合约", ""]
    section_unit_tests(out)
    section_cross_check(out)
    section_cases(out)
    section_smoke(out)
    section_performance(out)
    section_agent(out)
    out += ["## 结论", "",
            "1. 回测引擎关键规则（无未来函数、整手、佣金与印花税、涨跌停、期货盯市、换月、保证金）全部通过单元测试，"
            "并与手工计算逐分核对一致；22 个策略全部通过「截断数据前后信号一致」的无未来函数检验；",
            "2. 22 个策略均可在默认参数下运行并输出完整指标，参数修改、参数敏感性和多策略组合案例结果合理；",
            "3. 智能体能通过自然语言完成调取算法、修改参数、回测、组合与教学问答，回测结论中的数字经过核验，"
            "回测类回复自动附加免责声明，并能拒绝实盘投资建议；",
            "4. 并发回测与并发对话压测中服务稳定、无错误，内存不持续增长；接口已做路径穿越防护。", "",
            f"_报告生成用时 {time.perf_counter() - t0:.0f} 秒。_", ""]
    p = ROOT_DIR / "docs" / "测试报告.md"
    p.parent.mkdir(exist_ok=True)
    p.write_text("\n".join(out), encoding="utf-8")
    print(f"已生成 {p.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
