"""项目路径。所有运行时文件都放在仓库根目录的 data/ 下。"""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
DATA_DIR = ROOT_DIR / "data"
MARKET_DIR = DATA_DIR / "market"  # 行情快照（随仓库提交，保证回测可复现）
CACHE_DIR = DATA_DIR / "cache"  # 下载缓存（不提交）
STRATEGY_DIR = BACKEND_DIR / "quant" / "strategies"
