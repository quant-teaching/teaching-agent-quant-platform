"""策略标准接口。

每个策略是一个 Strategy 子类，放在 stock/ 或 futures/ 下，同名 .md 文件是它的教学说明。
新增策略只需三步：写子类 → 用 @register 注册 → 写同名 .md 文档，框架会自动发现它，
智能体工具、前端参数表单、参数校验全部由 Params 模型自动生成。

策略的唯一职责：根据截至 t 日收盘的行情，给出 t 日收盘后的目标权重。
成交、手续费、滑点、涨跌停都由回测引擎处理，策略不用关心。
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, ValidationError

from ..data.loader import AssetType, Bars

Category = Literal["stock", "futures"]


class StrategyParams(BaseModel):
    """参数模型基类。字段的 title 是中文名，description 说明含义和调参影响。"""

    model_config = ConfigDict(extra="forbid")


@dataclass
class StrategyOutput:
    weights: pd.DataFrame  # 日期 × 标的，目标权重
    rebalance: pd.Series | None = None  # 为 True 的日期强制把所有标的调回目标权重
    indicators: dict[str, pd.DataFrame] = field(default_factory=dict)  # 用于图表叠加的指标线
    notes: list[str] = field(default_factory=list)


class ParamError(ValueError):
    """参数不合法。消息面向学习者。"""


class Strategy(ABC):
    id: ClassVar[str]
    name: ClassVar[str]
    category: ClassVar[Category]
    style: ClassVar[str]  # 趋势跟踪 / 均值回归 / 截面选股 / 套利 ...
    summary: ClassVar[str]  # 一句话说明
    aliases: ClassVar[tuple[str, ...]] = ()  # 自然语言调取时的别名
    Params: ClassVar[type[StrategyParams]]
    default_universe: ClassVar[str]
    asset_types: ClassVar[frozenset[AssetType]]
    min_symbols: ClassVar[int] = 1

    def __init__(self, params: dict[str, Any] | StrategyParams | None = None):
        if isinstance(params, StrategyParams):
            self.params = params
        else:
            try:
                self.params = self.Params(**(params or {}))
            except ValidationError as e:
                raise ParamError(format_validation_error(self.Params, e)) from e

    @classmethod
    def expand_universe(cls, symbols: list[str]) -> list[str]:
        """需要额外标的的策略（如跨期套利需要次主力腿）在这里补充。"""
        return symbols

    @abstractmethod
    def generate(self, bars: Bars) -> StrategyOutput: ...

    @classmethod
    def doc_path(cls) -> Path:
        return Path(inspect.getfile(cls)).with_suffix(".md")

    @classmethod
    def doc(cls) -> str:
        p = cls.doc_path()
        return p.read_text(encoding="utf-8") if p.exists() else ""

    @classmethod
    def source(cls) -> str:
        return Path(inspect.getfile(cls)).read_text(encoding="utf-8")

    @classmethod
    def param_specs(cls) -> list[dict[str, Any]]:
        """参数说明列表：键名、中文名、类型、默认值、取值范围、说明。"""
        schema = cls.Params.model_json_schema()
        out = []
        for key, prop in schema.get("properties", {}).items():
            field_info = cls.Params.model_fields[key]
            spec = {
                "key": key,
                "title": prop.get("title", key),
                "type": prop.get("type", "string"),
                "default": field_info.default,
                "description": prop.get("description", ""),
            }
            for k_src, k_dst in (("minimum", "min"), ("maximum", "max"),
                                 ("exclusiveMinimum", "gt"), ("exclusiveMaximum", "lt"),
                                 ("enum", "options")):
                if k_src in prop:
                    spec[k_dst] = prop[k_src]
            if "enum" not in prop and "anyOf" not in prop and "$ref" in prop:
                ref = prop["$ref"].split("/")[-1]
                spec["options"] = schema["$defs"][ref].get("enum")
            if "allOf" in prop:
                ref = prop["allOf"][0]["$ref"].split("/")[-1]
                spec["options"] = schema["$defs"][ref].get("enum")
            out.append(spec)
        return out

    @classmethod
    def info(cls) -> dict[str, Any]:
        return {
            "id": cls.id,
            "name": cls.name,
            "category": cls.category,
            "category_label": "股票" if cls.category == "stock" else "期货",
            "style": cls.style,
            "summary": cls.summary,
            "aliases": list(cls.aliases),
            "default_universe": cls.default_universe,
            "asset_types": sorted(cls.asset_types),
            "min_symbols": cls.min_symbols,
            "params": cls.param_specs(),
        }


def format_validation_error(model: type[BaseModel], e: ValidationError) -> str:
    titles = {k: (f.title or k) for k, f in model.model_fields.items()}
    parts = []
    for err in e.errors():
        loc = err["loc"][0] if err["loc"] else ""
        if err["type"] == "extra_forbidden":
            parts.append(f"没有名为 {loc} 的参数（可用参数：{', '.join(model.model_fields)}）")
            continue
        name = f"{titles.get(loc, loc)}（{loc}）" if loc else "参数"
        ctx = err.get("ctx", {})
        if err["type"] in ("greater_than_equal", "greater_than"):
            parts.append(f"{name} 不能小于{'等于' if err['type'] == 'greater_than' else ''} {ctx.get('ge', ctx.get('gt'))}")
        elif err["type"] in ("less_than_equal", "less_than"):
            parts.append(f"{name} 不能大于{'等于' if err['type'] == 'less_than' else ''} {ctx.get('le', ctx.get('lt'))}")
        elif err["type"] == "value_error":
            parts.append(str(ctx.get("error", err["msg"])))
        else:
            parts.append(f"{name}：{err['msg']}")
    return "；".join(parts)


REGISTRY: dict[str, type[Strategy]] = {}


def register(cls: type[Strategy]) -> type[Strategy]:
    if cls.id in REGISTRY:
        raise RuntimeError(f"策略 id 重复：{cls.id}")
    REGISTRY[cls.id] = cls
    return cls


_loaded = False


def load_all() -> dict[str, type[Strategy]]:
    """导入 stock/ 和 futures/ 下的全部模块，触发 @register。"""
    global _loaded
    if not _loaded:
        for sub in ("stock", "futures"):
            pkg = importlib.import_module(f"{__package__}.{sub}")
            for m in pkgutil.iter_modules(pkg.__path__):
                importlib.import_module(f"{pkg.__name__}.{m.name}")
        _loaded = True
    return REGISTRY


def get_strategy_class(strategy_id: str) -> type[Strategy]:
    load_all()
    if strategy_id not in REGISTRY:
        raise KeyError(f"算法库中没有 id 为 {strategy_id} 的策略")
    return REGISTRY[strategy_id]
