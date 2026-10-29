"""测试环境：数据库和回测存档放到临时目录，不影响本地数据；不读取真实的大模型密钥。"""

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="quant-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["RESULTS_DIR"] = str(_tmp / "results")
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["BACKTEST_WORKERS"] = "0"
