"""智能体工具。每个工具返回 (给模型的结果, 给前端的卡片)。

给模型的数字都预先格式化成字符串（如 "12.3%"、"0.72"），减少模型自行换算导致的错误；
事实核验也以这些字符串为准。
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from api import services
from quant.engine.config import BacktestConfig
from quant.strategies.base import ParamError

from . import knowledge

DEFAULT_START = "2022-01-01"
DEFAULT_END = "2025-12-31"


@dataclass
class SessionState:
    params: dict[str, dict[str, Any]] = field(default_factory=dict)  # 策略 id → 已修改的参数
    current: str | None = None  # 当前讨论的策略
    results: list[dict[str, str]] = field(default_factory=list)  # 最近的回测 {id, title, period}

    @classmethod
    def load(cls, raw: str) -> SessionState:
        d = json.loads(raw or "{}")
        return cls(params=d.get("params", {}), current=d.get("current"), results=d.get("results", []))

    def dump(self) -> str:
        return json.dumps({"params": self.params, "current": self.current, "results": self.results[-10:]},
                          ensure_ascii=False)


class ToolError(Exception):
    pass


def pct(x: float | None, nd: int = 1) -> str | None:
    return None if x is None else f"{x * 100:.{nd}f}%"


def num(x: float | None, nd: int = 2) -> str | None:
    if x is None:
        return None
    if x == float("inf"):
        return "∞（无亏损交易）"
    return f"{x:.{nd}f}"


def _param_titles(info: dict) -> dict[str, str]:
    return {p["key"]: p["title"] for p in info["params"]}


# ---------------------------------------------------------------- 工具定义

STRATEGY_ARG = {"type": "string", "description": "策略 id、中文名或用户的说法，如 turtle_futures、海龟交易、布林带股票"}
DATE_ARG = {"type": "string", "description": "YYYY-MM-DD"}
UNIVERSE_ARG = {"type": "string", "description": "标的池：stock_pool（教学股票池）、industries（申万一级行业）、"
                "futures（全部商品期货）或逗号分隔的代码，如 600519,000858 或 RB,CU,AU。不填用策略默认标的池"}

TOOLS: list[dict] = [
    {"type": "function", "function": {
        "name": "list_strategies", "description": "列出算法库中的策略（含用户保存的衍生策略）",
        "parameters": {"type": "object", "properties": {
            "category": {"type": "string", "enum": ["stock", "futures"], "description": "只看股票或期货策略"},
            "keyword": {"type": "string", "description": "按名称或风格筛选，如 趋势、均值回归"}}}}},
    {"type": "function", "function": {
        "name": "get_strategy",
        "description": "从算法库调取一个策略：返回原理、交易规则、适用场景、局限性、全部可调参数（默认值、当前值、取值范围）",
        "parameters": {"type": "object", "properties": {"strategy": STRATEGY_ARG}, "required": ["strategy"]}}},
    {"type": "function", "function": {
        "name": "update_params",
        "description": "修改策略参数（保存在当前会话，后续回测自动使用），返回修改前后的对比。参数键名必须使用 get_strategy 返回的 key",
        "parameters": {"type": "object", "properties": {
            "strategy": STRATEGY_ARG,
            "changes": {"type": "object", "description": "只放要修改的参数键值，如 {\"atr_period\": 22, \"position_limit\": 0.15}"},
            "reason": {"type": "string", "description": "修改理由（可选，写在这里，不要放进 changes）"}},
            "required": ["strategy", "changes"]}}},
    {"type": "function", "function": {
        "name": "reset_params", "description": "把策略参数恢复为默认值",
        "parameters": {"type": "object", "properties": {"strategy": STRATEGY_ARG}, "required": ["strategy"]}}},
    {"type": "function", "function": {
        "name": "run_backtest",
        "description": "对单个策略执行历史回测，使用会话中已修改的参数。返回全套量化指标、基准对比和诊断数据；界面会自动显示图表",
        "parameters": {"type": "object", "properties": {
            "strategy": STRATEGY_ARG,
            "start": DATE_ARG, "end": DATE_ARG,
            "universe": UNIVERSE_ARG,
            "params": {"type": "object", "description": "本次回测临时覆盖的参数（不保存）"},
            "initial_capital": {"type": "number", "description": "初始资金（元），默认 1000 万"},
            "benchmarks": {"type": "array", "items": {"type": "string", "enum": ["000300", "000905", "399006"]},
                           "description": "对比基准：000300 沪深300、000905 中证500、399006 创业板指，默认三个都要"},
        }, "required": ["strategy", "start", "end"]}}},
    {"type": "function", "function": {
        "name": "run_portfolio_backtest",
        "description": "多策略组合回测：各子策略独立回测后按权重合成，返回组合与各子策略指标、相关性和分散化分析",
        "parameters": {"type": "object", "properties": {
            "components": {"type": "array", "minItems": 2, "maxItems": 8, "items": {"type": "object", "properties": {
                "strategy": STRATEGY_ARG,
                "weight": {"type": "number", "description": "自定义权重，等权组合时全部不填"},
                "params": {"type": "object", "description": "该子策略的临时参数"},
                "universe": UNIVERSE_ARG}, "required": ["strategy"]}},
            "start": DATE_ARG, "end": DATE_ARG,
            "rebalance": {"type": "string", "enum": ["none", "M", "Q"],
                          "description": "组合再平衡：none 不调仓、M 每月（默认）、Q 每季度"},
        }, "required": ["components", "start", "end"]}}},
    {"type": "function", "function": {
        "name": "get_backtest_detail",
        "description": "查看某次回测的更多细节：交易明细、年度/月度收益、回撤区间、行情分段、期末持仓",
        "parameters": {"type": "object", "properties": {
            "result_id": {"type": "string"},
            "section": {"type": "string", "enum": ["trades", "yearly", "monthly", "drawdowns", "regimes", "holdings"]}},
            "required": ["result_id", "section"]}}},
    {"type": "function", "function": {
        "name": "compare_params",
        "description": "参数敏感性对比：同一策略只改变一个参数，分别回测并对比指标，用于验证优化建议是否有效、检查过拟合",
        "parameters": {"type": "object", "properties": {
            "strategy": STRATEGY_ARG,
            "param": {"type": "string", "description": "参数 key"},
            "values": {"type": "array", "minItems": 2, "maxItems": 6, "items": {}},
            "start": DATE_ARG, "end": DATE_ARG, "universe": UNIVERSE_ARG,
        }, "required": ["strategy", "param", "values", "start", "end"]}}},
    {"type": "function", "function": {
        "name": "robustness_test",
        "description": "参数稳健性检验（防过拟合）：在 1~2 个参数的取值网格上回测，按分割日切成样本内/样本外，"
                       "检查样本内最优参数到样本外是否仍然好、参数优劣排序是否一致、哪组参数处在高原上。"
                       "学生问到过拟合、参数是否可靠、最优参数怎么选时使用",
        "parameters": {"type": "object", "properties": {
            "strategy": STRATEGY_ARG,
            "param_x": {"type": "string", "description": "第一个参数 key"},
            "values_x": {"type": "array", "minItems": 2, "maxItems": 7, "items": {}},
            "param_y": {"type": "string", "description": "第二个参数 key（可选，给了就做二维网格）"},
            "values_y": {"type": "array", "maxItems": 6, "items": {}},
            "start": DATE_ARG, "end": DATE_ARG,
            "split": {"type": "string", "description": "样本内/样本外分割日 YYYY-MM-DD，不填取区间前 70%"},
            "metric": {"type": "string", "enum": ["sharpe", "annual_return", "max_drawdown", "calmar"],
                       "description": "评价指标，默认夏普比率"},
            "universe": UNIVERSE_ARG,
        }, "required": ["strategy", "param_x", "values_x", "start", "end"]}}},
    {"type": "function", "function": {
        "name": "save_derived_strategy",
        "description": "把某个策略连同当前修改过的参数另存为一个新的衍生策略，之后可以按名字调取",
        "parameters": {"type": "object", "properties": {
            "base": STRATEGY_ARG,
            "name": {"type": "string", "description": "新策略名称"},
            "params": {"type": "object", "description": "额外修改的参数"},
            "description": {"type": "string"}}, "required": ["base", "name"]}}},
    {"type": "function", "function": {
        "name": "search_knowledge",
        "description": "检索平台教学知识库（全部策略的原理文档、量化指标解释、回测概念与陷阱），回答教学问题前使用",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "get_market_info",
        "description": "查看平台可用的数据范围、股票池成分、期货品种、申万行业列表",
        "parameters": {"type": "object", "properties": {}}}},
]

TOOL_LABELS = {
    "list_strategies": "查看算法库", "get_strategy": "调取策略", "update_params": "修改参数",
    "reset_params": "恢复默认参数", "run_backtest": "执行回测", "run_portfolio_backtest": "组合回测",
    "get_backtest_detail": "查看回测细节", "compare_params": "参数对比实验", "robustness_test": "稳健性检验", "save_derived_strategy": "保存衍生策略",
    "search_knowledge": "检索知识库", "get_market_info": "查看数据范围",
}


# ---------------------------------------------------------------- 工具实现

# 模型有时会把修改理由等说明文字塞进参数字典，这些键不是策略参数，直接丢掉而不是报错
META_KEYS = {"reason", "reasons", "note", "notes", "comment", "explanation", "why", "description",
             "说明", "理由", "原因", "备注"}


def _drop_meta(d: dict[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in (d or {}).items() if k not in META_KEYS}


class Toolbox:
    def __init__(self, state: SessionState, session_id: str):
        self.state = state
        self.session_id = session_id

    def call(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        fn = getattr(self, f"t_{name}", None)
        if fn is None:
            raise ToolError(f"没有名为 {name} 的工具")
        # 忽略工具定义之外的多余参数（如模型自行附加的 reason），避免整次调用失败
        accepted = inspect.signature(fn).parameters
        return fn(**{k: v for k, v in args.items() if k in accepted})

    # -- 策略

    def t_list_strategies(self, category: str | None = None, keyword: str | None = None):
        items = services.catalog()
        if category:
            items = [i for i in items if i["category"] == category]
        if keyword:
            items = [i for i in items if keyword in i["name"] or keyword in i["style"] or keyword in i["summary"]]
        data = [{"id": i["id"], "name": i["name"], "category": i["category_label"], "style": i["style"],
                 "summary": i["summary"], "derived": i.get("derived", False)} for i in items]
        return {"count": len(data), "strategies": data}, {"kind": "strategy_list", "items": data}

    def _entry(self, ref: str):
        try:
            return services.get_entry(ref)
        except services.NotFound as e:
            raise ToolError(str(e)) from e

    def _current_params(self, entry) -> dict[str, Any]:
        return {**entry.base_params, **self.state.params.get(entry.id, {})}

    def t_get_strategy(self, strategy: str):
        entry = self._entry(strategy)
        info = entry.info()
        cur = self._current_params(entry)
        defaults = {p["key"]: p["default"] for p in info["params"]}
        params = []
        for p in info["params"]:
            item = {k: p[k] for k in ("key", "title", "default", "description") if k in p}
            for k in ("min", "max", "gt", "lt", "options"):
                if k in p:
                    item[k] = p[k]
            item["current"] = cur.get(p["key"], p["default"])
            params.append(item)
        secs = knowledge.strategy_sections(entry.cls.id)
        # 教学文档里与"讲讲这个策略"最相关的小节（新旧两套标题都兼容）
        wanted = ("一句话理解", "概述", "原理", "交易规则（平台实现）", "交易规则", "什么行情好用，什么行情吃亏",
                  "适用场景", "局限性", "常见误区")
        doc = {k: secs[k] for k in wanted if k in secs}
        self.state.current = entry.id
        modified = {k: v for k, v in cur.items() if defaults.get(k) != v}
        result = {"id": entry.id, "name": entry.name, "category": info["category_label"], "style": info["style"],
                  "summary": info["summary"], "default_universe": info["default_universe"],
                  "params": params, "modified_params": modified, "doc": doc}
        if entry.derived:
            result["base_strategy"] = entry.cls.name
        card = {"kind": "strategy", "id": entry.id, "name": entry.name, "category": info["category"],
                "style": info["style"], "summary": info["summary"], "params": params}
        return result, card

    def _validate(self, entry, params: dict[str, Any]) -> dict[str, Any]:
        params = _drop_meta(params)
        try:
            return entry.cls(params).params.model_dump()
        except ParamError as e:
            raise ToolError(f"参数不合法：{e}") from e

    def t_update_params(self, strategy: str, changes: dict[str, Any], reason: str | None = None):
        entry = self._entry(strategy)
        changes = _drop_meta(changes)
        if not changes:
            raise ToolError("没有提供要修改的参数")
        before = self._validate(entry, self._current_params(entry))
        after = self._validate(entry, {**self._current_params(entry), **changes})
        titles = _param_titles(entry.info())
        diff = [{"key": k, "title": titles.get(k, k), "old": before.get(k), "new": after[k]}
                for k in changes if before.get(k) != after.get(k)]
        saved = {k: v for k, v in after.items() if k in self.state.params.get(entry.id, {}) or k in changes}
        self.state.params[entry.id] = {**self.state.params.get(entry.id, {}), **saved}
        self.state.current = entry.id
        result = {"strategy": entry.name, "changes": diff, "current_params": after,
                  "note": "已保存到当前会话，后续回测会使用新参数" if diff else "参数值与当前一致，没有变化"}
        return result, {"kind": "param_diff", "strategy": entry.name, "strategy_id": entry.id, "changes": diff}

    def t_reset_params(self, strategy: str):
        entry = self._entry(strategy)
        self.state.params.pop(entry.id, None)
        params = self._validate(entry, entry.base_params)
        return {"strategy": entry.name, "params": params, "note": "已恢复默认参数"}, \
            {"kind": "param_reset", "strategy": entry.name}

    # -- 回测

    def _config(self, start: str | None, end: str | None, **extra) -> dict[str, Any]:
        cfg = {"start": start or DEFAULT_START, "end": end or DEFAULT_END}
        cfg.update({k: v for k, v in extra.items() if v is not None})
        try:
            BacktestConfig(**cfg)
        except Exception as e:
            raise ToolError(f"回测设置不合法：{e}") from e
        return cfg

    def _remember(self, payload: dict[str, Any]) -> None:
        self.state.results.append({"id": payload["id"], "title": payload["title"],
                                   "period": f"{payload['config']['start']} ~ {payload['config']['end']}"})

    def t_run_backtest(self, strategy: str, start: str, end: str, universe: str | None = None,
                       params: dict[str, Any] | None = None, initial_capital: float | None = None,
                       benchmarks: list[str] | None = None):
        entry = self._entry(strategy)
        cur = self._current_params(entry)
        merged = self._validate(entry, {**cur, **(params or {})})
        cfg = self._config(start, end, initial_capital=initial_capital, benchmarks=benchmarks)
        try:
            payload = services.run_single(entry.id, merged, universe, cfg, session_id=self.session_id, source="chat")
        except (ParamError, ValueError) as e:
            raise ToolError(str(e)) from e
        self.state.current = entry.id
        self._remember(payload)
        defaults = {p["key"]: p["default"] for p in entry.info()["params"]}
        changed = {k: {"default": defaults.get(k), "used": v} for k, v in merged.items() if defaults.get(k) != v}
        return summarize_payload(payload, changed), {"kind": "backtest", "result_id": payload["id"],
                                                     "title": payload["title"], "metrics": _card_metrics(payload),
                                                     "period": f"{cfg['start']} ~ {cfg['end']}"}

    def t_run_portfolio_backtest(self, components: list[dict[str, Any]], start: str, end: str,
                                 rebalance: str = "M"):
        comps = []
        for c in components:
            entry = self._entry(c.get("strategy", ""))
            params = self._validate(entry, {**self._current_params(entry), **(c.get("params") or {})})
            comps.append({"strategy": entry.id, "params": params, "weight": c.get("weight"),
                          "universe": c.get("universe")})
        cfg = self._config(start, end)
        try:
            payload = services.run_portfolio_service(comps, cfg, rebalance or "M", session_id=self.session_id,
                                                     source="chat")
        except (ParamError, ValueError) as e:
            raise ToolError(str(e)) from e
        self._remember(payload)
        res = summarize_payload(payload, {})
        res["components"] = [
            {"name": c["label"], "weight": pct(c["weight"], 0), "result_id": c["result_id"],
             **{k: (pct(v) if k not in ("sharpe", "calmar", "trade_count") else
                    (v if k == "trade_count" else num(v))) for k, v in c["metrics"].items()}}
            for c in payload["components"]]
        div = payload["diagnostics"].get("diversification", {})
        res["diversification"] = {
            "相关系数矩阵": {"labels": div.get("labels"), "matrix": [[num(x) for x in row]
                                                               for row in div.get("correlation", [])]},
            "平均相关系数": num(div.get("avg_correlation")),
            "分散化比率": num(div.get("diversification_ratio")),
            "子策略加权平均波动率": pct(div.get("weighted_avg_vol")),
            "组合波动率": pct(div.get("portfolio_vol")),
            "风险贡献": {lb: pct(v) for lb, v in zip(div.get("labels", []), div.get("risk_contribution", []))},
        }
        dvc = payload["diagnostics"].get("drawdown_vs_components", {})
        res["组合最大回撤是否小于所有子策略"] = dvc.get("better_than_best_single")
        res["rebalance"] = {"none": "不调仓", "M": "每月再平衡", "Q": "每季度再平衡"}[rebalance or "M"]
        card = {"kind": "portfolio", "result_id": payload["id"], "title": payload["title"],
                "metrics": _card_metrics(payload), "period": f"{cfg['start']} ~ {cfg['end']}",
                "components": [{"name": c["label"], "weight": c["weight"], "result_id": c["result_id"]}
                               for c in payload["components"]]}
        return res, card

    def t_get_backtest_detail(self, result_id: str, section: str):
        try:
            p = services.load_payload(result_id)
        except services.NotFound as e:
            raise ToolError(str(e)) from e
        d = p["diagnostics"]
        if section == "trades":
            closed = [t for t in p["trades"] if not t["is_open"]]
            worst = sorted(closed, key=lambda t: t["pnl"])[:5]
            best = sorted(closed, key=lambda t: t["pnl"], reverse=True)[:5]
            fmt = lambda t: {"标的": t["name"], "方向": t["side"], "开仓": t["entry_date"], "平仓": t["exit_date"],  # noqa: E731
                             "持仓天数": t["holding_days"], "盈亏(元)": round(t["pnl"]), "收益率": pct(t["return_pct"])}
            data = {"已平仓交易数": len(closed), "最赚钱的5笔": [fmt(t) for t in best],
                    "最亏钱的5笔": [fmt(t) for t in worst],
                    "持仓中": [fmt(t) for t in p["trades"] if t["is_open"]][:10]}
        elif section == "yearly":
            y = p["yearly"]
            data = {str(yr): {c: pct(v[i]) for c, v in y["columns"].items()} for i, yr in enumerate(y["years"])}
        elif section == "monthly":
            data = {m["month"]: pct(m["ret"]) for m in p["monthly"]}
        elif section == "drawdowns":
            data = [{"回撤": pct(x["drawdown"]), "高点": x["peak"], "低点": x["trough"],
                     "恢复": x["recovery"] or "未恢复", "持续交易日": x["days"]} for x in d.get("top_drawdowns", [])]
        elif section == "regimes":
            data = _regimes(d)
        elif section == "holdings":
            data = [{"标的": h["name"], "权重": pct(h["weight"]), "数量": h["qty"]} for h in p["holdings_last"]]
        else:
            raise ToolError("section 不支持")
        return {"result_id": result_id, "section": section, "data": data}, None

    def t_compare_params(self, strategy: str, param: str, values: list[Any], start: str, end: str,
                         universe: str | None = None):
        entry = self._entry(strategy)
        titles = _param_titles(entry.info())
        if param not in titles:
            raise ToolError(f"{entry.name} 没有参数 {param}，可用参数：{', '.join(titles)}")
        cur = self._current_params(entry)
        cfg = self._config(start, end)
        rows, ids = [], []
        for v in values[:6]:
            params = self._validate(entry, {**cur, param: v})
            payload = services.run_single(entry.id, params, universe, cfg, session_id=self.session_id, source="chat")
            m = payload["metrics"]
            ids.append(payload["id"])
            rows.append({titles[param]: v, "年化收益率": pct(m["annual_return"]), "最大回撤": pct(m["max_drawdown"]),
                         "夏普比率": num(m["sharpe"]), "卡玛比率": num(m["calmar"]), "胜率": pct(m["win_rate"]),
                         "交易次数": m["trade_count"], "成本占比": pct(m["cost_ratio"], 2), "result_id": payload["id"]})
        res = {"strategy": entry.name, "param": param, "param_title": titles[param],
               "period": f"{cfg['start']} ~ {cfg['end']}", "other_params": {k: v for k, v in cur.items() if k != param},
               "results": rows}
        return res, {"kind": "param_compare", "strategy": entry.name, "param": titles[param], "rows": rows,
                     "result_ids": ids}

    def t_robustness_test(self, strategy: str, param_x: str, values_x: list[Any], start: str, end: str,
                          param_y: str | None = None, values_y: list[Any] | None = None, split: str | None = None,
                          metric: str = "sharpe", universe: str | None = None):
        entry = self._entry(strategy)
        cfg = self._config(start, end)
        try:
            out = services.robustness(entry.id, self._current_params(entry), universe, cfg["start"], cfg["end"],
                                      param_x, values_x, param_y or None, values_y if param_y else None, split, metric)
        except (ParamError, ValueError) as e:
            raise ToolError(str(e)) from e
        m = out["metric"]
        f = (lambda v: pct(v)) if m in ("annual_return", "max_drawdown") else (lambda v: num(v))

        def brief(c):
            return {"参数": {out["x"]["title"]: c["x"], **({out["y"]["title"]: c["y"]} if out["y"] else {})},
                    "样本内": f(c["train"][m]) if c.get("train") else None,
                    "样本外": f(c["test"][m]) if c.get("test") else None,
                    "样本外排名": c.get("test_rank")}
        res = {"strategy": entry.name, "metric": out["metric_label"],
               "sample_in": f"{cfg['start']} ~ {out['split']} 之前", "sample_out": f"{out['split']} ~ {cfg['end']}",
               "valid_combinations": out["count"],
               "best_in_sample": brief(out["best_train"]), "plateau": brief(out["robust"]),
               "default_params": {"样本内": f(out["default"]["train"][m]) if out["default"].get("train") else None,
                                  "样本外": f(out["default"]["test"][m]) if out["default"].get("test") else None},
               "rank_correlation": num(out["spearman"]),
               "grid": [{"参数": brief(c)["参数"], "样本内": f(c["train"][m]), "样本外": f(c["test"][m])}
                        for c in out["cells"] if c["ok"]],
               "conclusions": out["conclusions"],
               "note": "界面已显示样本内/样本外热力图。讲解时说明过拟合的含义，并建议选参数高原而不是孤立最高点"}
        return res, {"kind": "robustness", **out}

    def t_save_derived_strategy(self, base: str, name: str, params: dict[str, Any] | None = None,
                                description: str = ""):
        entry = self._entry(base)
        merged = {**self._current_params(entry), **(params or {})}
        try:
            info = services.save_derived(entry.id, name, merged, description)
        except ParamError as e:
            raise ToolError(str(e)) from e
        return {"id": info["id"], "name": info["name"], "base": entry.name, "params": merged,
                "note": "已保存到算法库，可以直接按名字调取或回测"}, \
            {"kind": "derived_saved", "id": info["id"], "name": info["name"], "base": entry.name}

    def t_search_knowledge(self, query: str):
        hits = knowledge.search(query, k=4)
        return {"query": query, "results": [{"来源": f"{h['source']} / {h['section']}", "内容": h["text"][:1200]}
                                            for h in hits]}, \
            {"kind": "knowledge", "query": query, "sources": [f"{h['source']} / {h['section']}" for h in hits]}

    def t_get_market_info(self):
        o = services.market_overview()
        return {"数据范围": o["ranges"], "标的池预设": o["universe_presets"],
                "股票池": [f"{s['symbol']} {s['name']}（{s['industry']}）" for s in o["stocks"]],
                "期货品种": [f"{f['symbol']} {f['name']}（{f['exchange']}，{f['sector']}）" for f in o["futures"]],
                "申万一级行业": [f"{i['symbol']} {i['name']}" for i in o["industries"]],
                "基准": o["benchmarks"]}, None


def _card_metrics(p: dict[str, Any]) -> dict[str, Any]:
    m = p["metrics"]
    keys = ("total_return", "annual_return", "max_drawdown", "sharpe", "calmar", "volatility", "win_rate",
            "profit_loss_ratio", "trade_count")
    out = {k: m.get(k) for k in keys}
    hs = p["benchmarks"].get("000300")
    if hs:
        out["hs300_annual_return"] = hs["annual_return"]
        out["hs300_max_drawdown"] = hs["max_drawdown"]
    return out


def _regimes(d: dict[str, Any]) -> dict[str, Any]:
    reg = d.get("regimes") or {}
    return {k: {"月数": v["months"], "策略平均月收益": pct(v["strategy_avg_monthly"], 2),
                "基准平均月收益": pct(v["benchmark_avg_monthly"], 2),
                "策略盈利月占比": pct(v["strategy_win_months"], 0)} for k, v in reg.items()}


def summarize_payload(p: dict[str, Any], changed: dict[str, Any]) -> dict[str, Any]:
    """把回测结果压缩成给模型看的摘要。"""
    m = p["metrics"]
    d = p["diagnostics"]
    metrics = {
        "总收益率": pct(m["total_return"]), "年化收益率": pct(m["annual_return"]),
        "最大回撤": pct(m["max_drawdown"]), "夏普比率": num(m["sharpe"]), "卡玛比率": num(m["calmar"]),
        "年化波动率": pct(m["volatility"]), "胜率": pct(m["win_rate"]), "盈亏比": num(m.get("profit_loss_ratio")),
        "交易次数": m.get("trade_count"), "索提诺比率": num(m["sortino"]),
        "最大回撤持续交易日": m["max_drawdown_days"],
        "最大回撤区间": f"{m.get('max_drawdown_peak')} → {m.get('max_drawdown_trough')}",
        "平均持仓天数": num(m.get("avg_holding_days"), 1), "平均仓位(敞口)": pct(m["avg_gross_exposure"], 0),
        "持仓时间占比": pct(d.get("time_in_market"), 0), "年化换手率": num(m["annual_turnover"], 1) + " 倍",
        "交易成本占初始资金": pct(m["cost_ratio"], 2), "期末权益(元)": round(m["final_equity"]),
    }
    bench = {}
    for b in p["benchmarks"].values():
        bench[b["name"]] = {"年化收益率": pct(b["annual_return"]), "最大回撤": pct(b["max_drawdown"]),
                            "夏普比率": num(b["sharpe"]), "策略年化超额": pct(b["excess_annual_return"]),
                            "贝塔": num(b.get("beta")), "相关系数": num(b.get("correlation"))}
    diag: dict[str, Any] = {"行情分段表现（按{}月涨跌划分）".format(d.get("regime_benchmark", "基准")): _regimes(d),
                            "最大的几次回撤": [f"{pct(x['drawdown'])}（{x['peak']} → {x['trough']}，"
                                         f"{'已于 ' + x['recovery'] + ' 恢复' if x['recovery'] else '尚未恢复'}）"
                                         for x in d.get("top_drawdowns", [])]}
    if "max_consecutive_losses" in d:
        diag["最长连续亏损笔数"] = d["max_consecutive_losses"]
        diag["持仓不超过3天的交易占比"] = pct(d.get("short_trade_ratio"), 0)
        if d.get("short_trade_win_rate") is not None:
            diag["持仓不超过3天的交易胜率"] = pct(d["short_trade_win_rate"], 0)
        bt, wt = d.get("best_trade"), d.get("worst_trade")
        if bt:
            diag["最赚钱的一笔"] = f"{bt['name']} {bt['side']} {bt['entry']}→{bt['exit']} 收益率 {pct(bt['return_pct'])}"
        if wt:
            diag["最亏钱的一笔"] = f"{wt['name']} {wt['side']} {wt['entry']}→{wt['exit']} 收益率 {pct(wt['return_pct'])}"
        diag["盈利贡献最大"] = [c["name"] for c in d.get("top_contributors", [])]
        diag["亏损最多"] = [c["name"] for c in d.get("bottom_contributors", [])]
    if "long_pnl" in d:
        diag["多头交易合计盈亏(元)"] = round(d["long_pnl"])
        diag["空头交易合计盈亏(元)"] = round(d["short_pnl"])
    if d.get("blocked_orders"):
        diag["因涨跌停/停牌/资金不足未成交次数"] = d["blocked_orders"]
    diag["交易成本年化拖累"] = pct(d.get("cost_drag_annual"), 2)
    yearly = p["yearly"]
    years = {str(yr): pct(yearly["columns"]["策略"][i]) for i, yr in enumerate(yearly["years"])}
    return {
        "result_id": p["id"], "title": p["title"],
        "period": f"{p['config']['start']} ~ {p['config']['end']}",
        "universe": [u["name"] for u in p["universe"]][:12] + (["…"] if len(p["universe"]) > 12 else []),
        "universe_size": len(p["universe"]),
        "params_used": p["params"], "params_changed_from_default": changed,
        "metrics": metrics, "benchmarks": bench, "yearly_returns": years, "diagnostics": diag,
        "warnings": p["warnings"], "notes": p["notes"],
        "charts_shown": "界面已自动展示：净值曲线（叠加基准）、回撤曲线、年度收益柱状图、月度收益热力图、交易点位图",
    }


def today() -> str:
    return date.today().isoformat()
