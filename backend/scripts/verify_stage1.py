"""阶段 1 验证：搜索“太极实业”和“谷歌”，拉取最近 120 个交易日日 K，打印前后各 3 行。

运行（在 backend 目录下）：
    python -m scripts.verify_stage1
首次运行需要拉取美股符号表，约 10 分钟；之后走 SQLite 缓存。
"""
import logging
import time

import pandas as pd

from app.data import get_adapter, search_all

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
pd.set_option("display.width", 120)


def show(query: str, market: str) -> None:
    t0 = time.time()
    hits = search_all(query)
    print(f"\n### 搜索 “{query}” → {len(hits)} 条（{time.time() - t0:.1f}s）")
    for h in hits[:5]:
        print("   ", h)
    target = next(h for h in hits if h["market"] == market)
    adapter = get_adapter(market)
    df = adapter.kline(target["symbol"], days=120)
    print(f"\n{target['name']}（{target['symbol']}.{market}）日 K：共 {len(df)} 行，"
          f"{df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")
    print(df.head(3).to_string())
    print("...")
    print(df.tail(3).to_string())


if __name__ == "__main__":
    show("太极实业", "CN")
    show("谷歌", "US")
