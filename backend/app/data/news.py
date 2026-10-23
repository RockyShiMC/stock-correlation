"""新闻适配器。

- CN：东财个股新闻 stock_news_em（akshare 1.19.1 实测，每次返回最近约 10 条）。
- US：v1 未接入，返回空列表，并通过 note 在结果中注明。
"""
import akshare as ak
import pandas as pd

from app.data.base import retry

US_NEWS_NOTE = "美股新闻源未接入"


def cn_news(symbol: str) -> list[dict]:
    df = retry(lambda: ak.stock_news_em(symbol=symbol))
    items = []
    for _, r in df.iterrows():
        items.append({
            "title": str(r["新闻标题"]).strip(),
            "content": str(r["新闻内容"]).strip() if pd.notna(r["新闻内容"]) else "",
            "published_at": str(r["发布时间"]),
            "source": str(r["文章来源"]),
            "url": str(r["新闻链接"]),
        })
    return items


def us_news(symbol: str) -> list[dict]:
    return []


def get_news(symbol: str, market: str) -> tuple[list[dict], str | None]:
    """返回 (新闻列表, 备注)。备注非空时需要写进分析结果。"""
    if market == "CN":
        return cn_news(symbol), None
    return us_news(symbol), US_NEWS_NOTE
