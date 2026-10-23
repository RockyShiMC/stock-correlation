"""美股适配器。

接口均已在 akshare 1.19.1 上实测：
- 符号表：新浪 get_us_stock_name，含中文名（如“谷歌”→ GOOG，“谷歌A类股”→ GOOGL）。
  该接口逐页抓取约 900 页，全量一次约 10 分钟，所以缓存 7 天。
  东财 stock_us_spot_em 在开发环境网络下不可用。
- 日 K：新浪 stock_us_daily（代码直接用 GOOGL 这类 ticker）。
- 大盘：新浪 index_us_stock_sina(".NDX")，纳斯达克 100。
"""
import akshare as ak
import pandas as pd

from app.data.base import MarketAdapter, normalize_kline, normalize_text, retry

# 同一公司有多个代码时，搜索结果里默认排在最前的那个
PREFERRED = {"谷歌": "GOOGL"}


class USAdapter(MarketAdapter):
    market = "US"
    symbols_ttl = 7 * 86400
    index_name = "纳斯达克100"

    def search(self, q: str, limit: int = 20) -> list[dict]:
        results = super().search(q, limit)
        preferred = PREFERRED.get(normalize_text(q))
        if preferred:
            results.sort(key=lambda r: r["symbol"] != preferred)
        return results

    def _fetch_symbols(self):
        df = retry(lambda: ak.get_us_stock_name())
        rows: list[tuple[str, str, str | None]] = []
        for sym, en, cn in zip(df["symbol"], df["name"], df["cname"]):
            sym = str(sym).strip().upper()
            if not sym:
                continue
            en = str(en).strip() if pd.notna(en) else ""
            cn = str(cn).strip() if pd.notna(cn) else ""
            # 有中文名用中文名展示，英文名作为备用匹配名
            rows.append((sym, cn or en or sym, en if cn else None))
        return rows

    def kline(self, symbol: str, days: int = 120) -> pd.DataFrame:
        df = retry(lambda: ak.stock_us_daily(symbol=symbol.upper(), adjust="qfq"))
        return normalize_kline(df, days)

    def index_kline(self, days: int = 120) -> pd.DataFrame:
        df = retry(lambda: ak.index_us_stock_sina(symbol=".NDX"))
        return normalize_kline(df, days)
