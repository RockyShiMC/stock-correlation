"""阶段 2 验证：输出太极实业 vs 谷歌 A 类股的完整统计结果 JSON。

运行（在 backend 目录下）：
    python -m scripts.verify_stage2
"""
import json

from app.analysis.stats import collect_stats
from app.data import search_all


def pick(query: str, market: str) -> dict:
    hit = next(h for h in search_all(query) if h["market"] == market)
    return {"symbol": hit["symbol"], "market": market}


if __name__ == "__main__":
    a, b = pick("太极实业", "CN"), pick("谷歌", "US")
    print(json.dumps(collect_stats(a, b, days=120), ensure_ascii=False, indent=2))
