"""数据源适配层的统一接口与公共工具。"""
import logging
import time
import unicodedata
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Callable, TypeVar

import pandas as pd

from app.db import connect

log = logging.getLogger(__name__)

KLINE_COLUMNS = ["date", "open", "high", "low", "close", "volume"]

T = TypeVar("T")


def retry(fn: Callable[[], T], attempts: int = 3, delay: float = 1.5) -> T:
    """AKShare 背后的网页接口偶发断连，统一做有限次重试。"""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - 上游异常类型不固定
            last = e
            log.warning("数据源调用失败（第 %d 次）：%s", i + 1, e)
            if i < attempts - 1:
                time.sleep(delay * (i + 1))
    assert last is not None
    raise last


def normalize_text(s: str) -> str:
    """全角转半角、去空白、转大写，用于搜索匹配（深交所简称里有“万  科Ａ”这种写法）。"""
    return "".join(unicodedata.normalize("NFKC", str(s)).split()).upper()


def normalize_kline(df: pd.DataFrame, days: int) -> pd.DataFrame:
    """统一成 KLINE_COLUMNS，按日期升序，只保留最近 days 个交易日。"""
    out = df[KLINE_COLUMNS].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    for c in KLINE_COLUMNS[1:]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["close"]).sort_values("date").drop_duplicates("date")
    return out.tail(days).reset_index(drop=True)


def start_date_for(days: int) -> str:
    """交易日少于自然日，按 2 倍自然日再加缓冲往前取，足够覆盖节假日。"""
    return (datetime.now() - timedelta(days=days * 2 + 30)).strftime("%Y%m%d")


class MarketAdapter(ABC):
    market: str
    # 符号表多久刷新一次（秒）
    symbols_ttl: int = 86400

    @abstractmethod
    def _fetch_symbols(self) -> list[tuple[str, str, str | None]]:
        """从数据源拉取完整符号表：[(symbol, name, alt_name)]。"""

    @abstractmethod
    def kline(self, symbol: str, days: int = 120) -> pd.DataFrame:
        """日 K，列为 KLINE_COLUMNS，日期升序。"""

    @abstractmethod
    def index_kline(self, days: int = 120) -> pd.DataFrame:
        """所在市场大盘指数日 K，列同 kline。"""

    index_name: str

    # ---- 符号表缓存（SQLite） ----

    def _symbols_fresh(self, conn) -> bool:
        row = conn.execute(
            "SELECT updated_at FROM symbols_meta WHERE market=?", (self.market,)
        ).fetchone()
        if not row:
            return False
        updated = datetime.fromisoformat(row["updated_at"])
        return (datetime.now(timezone.utc) - updated).total_seconds() < self.symbols_ttl

    def ensure_symbols(self) -> None:
        with connect() as conn:
            if self._symbols_fresh(conn):
                return
            has_old = conn.execute(
                "SELECT 1 FROM symbols WHERE market=? LIMIT 1", (self.market,)
            ).fetchone()
        try:
            rows = self._fetch_symbols()
        except Exception:
            if has_old:
                log.exception("%s 符号表刷新失败，继续使用旧缓存", self.market)
                return
            raise
        with connect() as conn:
            conn.execute("DELETE FROM symbols WHERE market=?", (self.market,))
            conn.executemany(
                "INSERT OR REPLACE INTO symbols(market, symbol, name, alt_name) VALUES (?,?,?,?)",
                [(self.market, s, n, a) for s, n, a in rows],
            )
            conn.execute(
                "INSERT OR REPLACE INTO symbols_meta(market, updated_at) VALUES (?,?)",
                (self.market, datetime.now(timezone.utc).isoformat()),
            )

    def search(self, q: str, limit: int = 20) -> list[dict]:
        key = normalize_text(q)
        if not key:
            return []
        self.ensure_symbols()
        with connect() as conn:
            rows = conn.execute(
                "SELECT symbol, name, alt_name FROM symbols WHERE market=?", (self.market,)
            ).fetchall()

        scored: list[tuple[int, int, dict]] = []
        for r in rows:
            sym = normalize_text(r["symbol"])
            names = [normalize_text(r["name"])]
            if r["alt_name"]:
                names.append(normalize_text(r["alt_name"]))
            if sym == key:
                rank = 0
            elif key in names:
                rank = 1
            elif sym.startswith(key) or any(n.startswith(key) for n in names):
                rank = 2
            elif key in sym or any(key in n for n in names):
                rank = 3
            else:
                continue
            scored.append(
                (rank, len(r["name"]), {"symbol": r["symbol"], "name": r["name"], "market": self.market})
            )
        scored.sort(key=lambda x: (x[0], x[1]))
        return [item for _, _, item in scored[:limit]]

    def name_of(self, symbol: str) -> str | None:
        self.ensure_symbols()
        with connect() as conn:
            row = conn.execute(
                "SELECT name FROM symbols WHERE market=? AND symbol=?", (self.market, symbol)
            ).fetchone()
        return row["name"] if row else None
