"""标的目录：教学用股票池、基准指数、申万一级行业、商品期货品种规格。

股票池取自沪深 300 中各行业的代表性龙头（以 2026 年的成分为准），因此存在幸存者偏差：
这些公司是"活下来并且做大了"的样本，回测结果会比真实的历史选股更乐观。这一点本身就是教学内容。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Stock:
    code: str
    name: str
    industry: str  # 申万一级行业

    @property
    def sina_symbol(self) -> str:
        return ("sh" if self.code.startswith("6") else "sz") + self.code

    def limit_pct(self, on: date) -> float:
        """涨跌停幅度。创业板 2020-08-24 注册制改革后为 20%，科创板一直为 20%，其余主板 10%。"""
        if self.code.startswith("688"):
            return 0.20
        if self.code.startswith("300") and on >= date(2020, 8, 24):
            return 0.20
        return 0.10


STOCK_POOL: list[Stock] = [
    Stock("600036", "招商银行", "银行"),
    Stock("601398", "工商银行", "银行"),
    Stock("601166", "兴业银行", "银行"),
    Stock("000001", "平安银行", "银行"),
    Stock("601318", "中国平安", "非银金融"),
    Stock("600030", "中信证券", "非银金融"),
    Stock("601628", "中国人寿", "非银金融"),
    Stock("300059", "东方财富", "非银金融"),
    Stock("600519", "贵州茅台", "食品饮料"),
    Stock("000858", "五粮液", "食品饮料"),
    Stock("000568", "泸州老窖", "食品饮料"),
    Stock("600887", "伊利股份", "食品饮料"),
    Stock("603288", "海天味业", "食品饮料"),
    Stock("600276", "恒瑞医药", "医药生物"),
    Stock("000538", "云南白药", "医药生物"),
    Stock("300015", "爱尔眼科", "医药生物"),
    Stock("600436", "片仔癀", "医药生物"),
    Stock("000333", "美的集团", "家用电器"),
    Stock("000651", "格力电器", "家用电器"),
    Stock("600690", "海尔智家", "家用电器"),
    Stock("002415", "海康威视", "计算机"),
    Stock("002230", "科大讯飞", "计算机"),
    Stock("600588", "用友网络", "计算机"),
    Stock("000725", "京东方A", "电子"),
    Stock("002475", "立讯精密", "电子"),
    Stock("600584", "长电科技", "电子"),
    Stock("300750", "宁德时代", "电力设备"),
    Stock("601012", "隆基绿能", "电力设备"),
    Stock("600406", "国电南瑞", "电力设备"),
    Stock("300274", "阳光电源", "电力设备"),
    Stock("600104", "上汽集团", "汽车"),
    Stock("002594", "比亚迪", "汽车"),
    Stock("601899", "紫金矿业", "有色金属"),
    Stock("603993", "洛阳钼业", "有色金属"),
    Stock("600111", "北方稀土", "有色金属"),
    Stock("601088", "中国神华", "煤炭"),
    Stock("600028", "中国石化", "石油石化"),
    Stock("601857", "中国石油", "石油石化"),
    Stock("600309", "万华化学", "基础化工"),
    Stock("601668", "中国建筑", "建筑装饰"),
    Stock("601390", "中国中铁", "建筑装饰"),
    Stock("600585", "海螺水泥", "建筑材料"),
    Stock("601006", "大秦铁路", "交通运输"),
    Stock("601919", "中远海控", "交通运输"),
    Stock("601111", "中国国航", "交通运输"),
    Stock("600900", "长江电力", "公用事业"),
    Stock("600050", "中国联通", "通信"),
    Stock("000063", "中兴通讯", "通信"),
    Stock("000002", "万科A", "房地产"),
    Stock("600048", "保利发展", "房地产"),
    Stock("600760", "中航沈飞", "国防军工"),
    Stock("600893", "航发动力", "国防军工"),
    Stock("600019", "宝钢股份", "钢铁"),
    Stock("002714", "牧原股份", "农林牧渔"),
    Stock("300498", "温氏股份", "农林牧渔"),
]

STOCKS: dict[str, Stock] = {s.code: s for s in STOCK_POOL}


@dataclass(frozen=True)
class Index:
    code: str
    name: str
    sina_symbol: str


BENCHMARKS: list[Index] = [
    Index("000300", "沪深300", "sh000300"),
    Index("000905", "中证500", "sh000905"),
    Index("399006", "创业板指", "sz399006"),
]

INDEXES: dict[str, Index] = {i.code: i for i in BENCHMARKS}


@dataclass(frozen=True)
class FuturesSpec:
    """商品期货品种规格。保证金率、手续费率为教学近似值，实际以交易所和期货公司为准。"""

    code: str
    name: str
    exchange: str
    multiplier: int  # 合约乘数（每手多少单位）
    tick: float  # 最小变动价位
    margin_rate: float  # 保证金比例
    months: tuple[int, ...]  # 主力合约通常出现的月份
    sector: str
    commission_rate: float = 0.0001  # 按成交金额收取的手续费率


_ALL = tuple(range(1, 13))
_159 = (1, 5, 9)

FUTURES: list[FuturesSpec] = [
    FuturesSpec("RB", "螺纹钢", "SHFE", 10, 1, 0.10, (1, 5, 10), "黑色"),
    FuturesSpec("HC", "热轧卷板", "SHFE", 10, 1, 0.10, (1, 5, 10), "黑色"),
    FuturesSpec("I", "铁矿石", "DCE", 100, 0.5, 0.13, _159, "黑色"),
    FuturesSpec("J", "焦炭", "DCE", 100, 0.5, 0.15, _159, "黑色"),
    FuturesSpec("CU", "沪铜", "SHFE", 5, 10, 0.10, _ALL, "有色"),
    FuturesSpec("AL", "沪铝", "SHFE", 5, 5, 0.10, _ALL, "有色"),
    FuturesSpec("AU", "黄金", "SHFE", 1000, 0.02, 0.10, (2, 4, 6, 8, 10, 12), "贵金属"),
    FuturesSpec("M", "豆粕", "DCE", 10, 1, 0.08, _159, "农产品"),
    FuturesSpec("Y", "豆油", "DCE", 10, 2, 0.08, _159, "农产品"),
    FuturesSpec("P", "棕榈油", "DCE", 10, 2, 0.10, _159, "农产品"),
    FuturesSpec("CF", "棉花", "CZCE", 5, 5, 0.08, _159, "农产品"),
    FuturesSpec("SR", "白糖", "CZCE", 10, 1, 0.08, _159, "农产品"),
    FuturesSpec("TA", "PTA", "CZCE", 5, 2, 0.08, _159, "能源化工"),
    FuturesSpec("MA", "甲醇", "CZCE", 10, 1, 0.08, _159, "能源化工"),
    FuturesSpec("RU", "天然橡胶", "SHFE", 10, 5, 0.10, _159, "能源化工"),
    FuturesSpec("FG", "玻璃", "CZCE", 20, 1, 0.10, _159, "能源化工"),
]

FUTURES_SPECS: dict[str, FuturesSpec] = {f.code: f for f in FUTURES}

NEXT_LEG_SUFFIX = ".next"  # 次主力腿的代码后缀，如 RB.next


def futures_spec(symbol: str) -> FuturesSpec:
    return FUTURES_SPECS[symbol.removesuffix(NEXT_LEG_SUFFIX)]


def is_futures(symbol: str) -> bool:
    return symbol.removesuffix(NEXT_LEG_SUFFIX) in FUTURES_SPECS
