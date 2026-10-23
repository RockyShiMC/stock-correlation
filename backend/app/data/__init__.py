from app.data.base import KLINE_COLUMNS, MarketAdapter
from app.data.cn import CNAdapter
from app.data.us import USAdapter

ADAPTERS: dict[str, MarketAdapter] = {"CN": CNAdapter(), "US": USAdapter()}


def get_adapter(market: str) -> MarketAdapter:
    try:
        return ADAPTERS[market.upper()]
    except KeyError:
        raise ValueError(f"不支持的市场：{market}（只支持 CN / US）") from None


def search_all(q: str, limit: int = 20) -> list[dict]:
    """两个市场都搜，每个市场最多 limit 条，按 CN、US 顺序拼接。"""
    results: list[dict] = []
    for adapter in ADAPTERS.values():
        results += adapter.search(q, limit)
    return results


__all__ = ["KLINE_COLUMNS", "MarketAdapter", "ADAPTERS", "get_adapter", "search_all"]
