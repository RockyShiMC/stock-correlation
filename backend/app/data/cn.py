"""A 股适配器。

接口均已在 akshare 1.19.1 上实测：
- 符号表：stock_info_sh_name_code（主板A股、科创板）+ stock_info_sz_name_code（A股列表）
  北交所 stock_info_bj_name_code 在开发环境网络下不可用，v1 不纳入。
- 日 K：腾讯 stock_zh_a_hist_tx 为主（成交量单位：股）；
  东财 stock_zh_a_hist 为备用（成交量单位：手，换算为股）。东财接口在开发环境下时断时续。
- 大盘：新浪 stock_zh_index_daily("sh000300")，沪深 300。
"""
import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from app.data.base import MarketAdapter, normalize_kline, retry, start_date_for

log = logging.getLogger(__name__)


def _exchange_prefix(symbol: str) -> str:
    if symbol.startswith(("6", "9")):
        return "sh"
    if symbol.startswith(("4", "8")):
        return "bj"
    return "sz"


class CNAdapter(MarketAdapter):
    market = "CN"
    symbols_ttl = 86400
    index_name = "沪深300"

    def _fetch_symbols(self):
        rows: list[tuple[str, str, str | None]] = []
        for board in ("主板A股", "科创板"):
            df = retry(lambda: ak.stock_info_sh_name_code(symbol=board))
            rows += [(str(c).zfill(6), str(n).strip(), None) for c, n in zip(df["证券代码"], df["证券简称"])]
        df = retry(lambda: ak.stock_info_sz_name_code(symbol="A股列表"))
        rows += [
            (str(c).zfill(6), "".join(str(n).split()), None)
            for c, n in zip(df["A股代码"], df["A股简称"])
        ]
        return rows

    def kline(self, symbol: str, days: int = 120) -> pd.DataFrame:
        start = start_date_for(days)
        end = datetime.now().strftime("%Y%m%d")
        try:
            df = retry(
                lambda: ak.stock_zh_a_hist_tx(
                    symbol=_exchange_prefix(symbol) + symbol, start_date=start, end_date=end, adjust="qfq"
                )
            )
        except Exception:
            log.warning("腾讯日 K 获取失败，改用东财：%s", symbol)
            df = retry(
                lambda: ak.stock_zh_a_hist(
                    symbol=symbol, period="daily", start_date=start, end_date=end, adjust="qfq"
                )
            )
            df = df.rename(
                columns={"日期": "date", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume"}
            )
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce") * 100
        return normalize_kline(df, days)

    def index_kline(self, days: int = 120) -> pd.DataFrame:
        df = retry(lambda: ak.stock_zh_index_daily(symbol="sh000300"))
        return normalize_kline(df, days)
