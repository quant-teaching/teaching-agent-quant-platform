"""由各策略的 .md 教学文档和参数定义生成《算法库说明文档》（docs/算法库说明.md）。

用法（在 backend/ 下）：uv run python scripts/build_algorithm_doc.py
文档内容直接来自代码中的参数定义和同名 .md 文件，修改策略后重新运行即可保持一致。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.services import ORDER  # noqa: E402
from quant.paths import ROOT_DIR  # noqa: E402
from quant.strategies.base import load_all  # noqa: E402

UNIVERSE = {"stock_pool": "教学股票池（55 只）", "industries": "申万一级行业（31 个）", "futures": "商品期货（16 个品种）"}


def fmt(v) -> str:
    if isinstance(v, bool):
        return "开启" if v else "关闭"
    return str(v)


def main() -> None:
    reg = load_all()
    strategies = [reg[i] for i in ORDER if i in reg]
    stock = [c for c in strategies if c.category == "stock"]
    futures = [c for c in strategies if c.category == "futures"]
    lines = [
        "# 算法库说明文档",
        "",
        "> 本文档由 `backend/scripts/build_algorithm_doc.py` 根据代码中的参数定义和各策略的教学文档自动生成。",
        "> 所有回测结果仅用于算法学习与教学演示，不构成任何投资建议。",
        "",
        f"算法库共 **{len(strategies)}** 个策略：股票策略 {len(stock)} 个，期货 CTA 策略 {len(futures)} 个。",
        "每个策略都是 `Strategy` 的子类，代码位于 `backend/quant/strategies/{stock,futures}/`，同名 `.md` 为教学说明。",
        "",
        "## 总览",
        "",
        "| # | 策略 | 类别 | 风格 | 默认标的 | 参数数 | 源码 |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(strategies, 1):
        src = Path(c.doc_path()).with_suffix(".py").relative_to(ROOT_DIR)
        lines.append(f"| {i} | [{c.name}](#{i}-{c.name.replace(' ', '-').lower()}) | {'股票' if c.category == 'stock' else '期货'} "
                     f"| {c.style} | {UNIVERSE.get(c.default_universe, c.default_universe)} | {len(c.param_specs())} | `{src}` |")
    lines += ["", "## 统一接口", "",
              "所有策略只做一件事：根据截至 t 日收盘的行情，输出 t 日收盘后的**目标权重**（持仓名义市值 / 权益，期货可为负表示做空）。",
              "成交、手续费、滑点、涨跌停、保证金和期货换月都由回测引擎统一处理，策略代码不需要关心。",
              "", "```python", "class Strategy(ABC):",
              "    id: str; name: str; category: 'stock' | 'futures'; style: str; summary: str",
              "    aliases: tuple[str, ...]          # 自然语言调取时的别名",
              "    Params: type[StrategyParams]      # pydantic 参数模型：类型、默认值、范围、中文说明",
              "    default_universe: str             # 默认标的池",
              "    def generate(self, bars: Bars) -> StrategyOutput: ...  # 返回目标权重、调仓日、指标线",
              "```", ""]
    for i, c in enumerate(strategies, 1):
        doc = c.doc()
        doc = re.sub(r"^# .+\n", "", doc, count=1)
        doc = re.sub(r"^(#{2,3}) ", lambda m: "#" * (len(m.group(1)) + 2) + " ", doc, flags=re.M)
        params = ["| 参数键 | 中文名 | 默认值 | 取值范围 | 说明 |", "|---|---|---|---|---|"]
        for p in c.param_specs():
            lo = p.get("min", p.get("gt"))
            hi = p.get("max", p.get("lt"))
            rng = "、".join(p["options"]) if p.get("options") else (f"{lo} ~ {hi}" if lo is not None or hi is not None else "—")
            if p["type"] == "boolean":
                rng = "开启 / 关闭"
            params.append(f"| `{p['key']}` | {p['title']} | {fmt(p['default'])} | {rng} | {p['description']} |")
        lines += [
            f"## {i}. {c.name}", "",
            f"- **策略 id**：`{c.id}`　**类别**：{'股票' if c.category == 'stock' else '期货'}　**风格**：{c.style}",
            f"- **一句话说明**：{c.summary}",
            f"- **对话中可以这样调取**：{'、'.join('「' + a + '」' for a in c.aliases)}",
            "",
            "#### 参数定义（来自代码）", "", *params, "",
            doc.strip(), "", "---", "",
        ]
    out = ROOT_DIR / "docs" / "算法库说明.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"已生成 {out.relative_to(ROOT_DIR)}（{len(strategies)} 个策略）")


if __name__ == "__main__":
    main()
