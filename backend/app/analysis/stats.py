"""第一层：统计相关。纯代码计算，大模型不参与。

口径：
- 对齐：两只标的收盘价按日期内连接，只保留双方都有交易的日期，再在对齐后的序列上算日收益率。
- 相关：日收益率的 Pearson、Spearman（秩的 Pearson，平均秩处理并列）。
- 滚动相关：对齐后日收益率的 20 日、60 日窗口 Pearson。
- 领先滞后（仅跨市场）：A 股 T+1 日收益 vs 美股 T 日收益。各自用本市场交易日历算日收益；
  对每个美股交易日 T，取其后第一个 A 股交易日作为 T+1；若多个美股交易日对应同一个 A 股交易日
  （A 股休市期间），只保留最近的那个美股交易日。
- 大盘对照：每只标的与所在市场指数（CN 沪深300、US 纳斯达克100）按同样方法对齐后的日收益率 Pearson。
"""
import math
from datetime import datetime, timezone

import pandas as pd

from app.data import get_adapter

ROUND = 4


def _num(x) -> float | None:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), ROUND)


def close_series(df: pd.DataFrame) -> pd.Series:
    """kline DataFrame → 以日期字符串为索引的收盘价序列（升序、去重）。"""
    s = pd.Series(df["close"].astype(float).values, index=df["date"].astype(str).values)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.dropna()


def align_closes(a: pd.Series, b: pd.Series) -> pd.DataFrame:
    """只保留双方都有交易的日期，返回列 a、b 的收盘价表。"""
    return pd.concat({"a": a, "b": b}, axis=1, join="inner").sort_index()


def returns(closes: pd.DataFrame | pd.Series):
    return closes.pct_change().iloc[1:]


def pearson(x: pd.Series, y: pd.Series) -> float | None:
    if len(x) < 3:
        return None
    return _num(x.corr(y, method="pearson"))


def spearman(x: pd.Series, y: pd.Series) -> float | None:
    if len(x) < 3:
        return None
    return _num(x.rank(method="average").corr(y.rank(method="average"), method="pearson"))


def rolling_corr(ret: pd.DataFrame, window: int) -> list[float | None]:
    return [_num(v) for v in ret["a"].rolling(window).corr(ret["b"])]


def lead_lag_pairs(cn_close: pd.Series, us_close: pd.Series) -> pd.DataFrame:
    """配对 (A 股 T+1 日收益, 美股 T 日收益)，返回列 cn_date、us_date、cn_ret、us_ret。"""
    cn_ret = returns(cn_close)
    us_ret = returns(us_close)
    cn_dates = list(cn_ret.index)
    rows = []
    for t, r in us_ret.items():
        # 第一个严格晚于 T 的 A 股交易日
        i = pd.Index(cn_dates).searchsorted(t, side="right")
        if i >= len(cn_dates):
            continue
        d = cn_dates[i]
        rows.append({"cn_date": d, "us_date": t, "cn_ret": cn_ret[d], "us_ret": r})
    pairs = pd.DataFrame(rows, columns=["cn_date", "us_date", "cn_ret", "us_ret"])
    # 同一 A 股交易日只保留最近的美股交易日
    return pairs.drop_duplicates("cn_date", keep="last").reset_index(drop=True)


def benchmark_corr(stock: pd.Series, index: pd.Series) -> dict:
    aligned = align_closes(stock, index)
    ret = returns(aligned)
    return {"pearson": pearson(ret["a"], ret["b"]), "sample_days": len(aligned)}


def compute_stats(
    a_info: dict,
    a_kline: pd.DataFrame,
    a_index: pd.DataFrame,
    b_info: dict,
    b_kline: pd.DataFrame,
    b_index: pd.DataFrame,
    days: int,
) -> dict:
    """a_info / b_info: {symbol, market, name, index_name}。不做任何网络请求。"""
    a_close, b_close = close_series(a_kline), close_series(b_kline)
    aligned = align_closes(a_close, b_close)
    ret = returns(aligned)

    def side(info, close):
        return {
            **info,
            "raw_days": len(close),
            "first_date": close.index[0] if len(close) else None,
            "last_date": close.index[-1] if len(close) else None,
        }

    markets = {a_info["market"], b_info["market"]}
    if markets == {"CN", "US"}:
        cn_close, us_close = (a_close, b_close) if a_info["market"] == "CN" else (b_close, a_close)
        pairs = lead_lag_pairs(cn_close, us_close)
        lead_lag = {
            "applicable": True,
            "description": "A股 T+1 日收益率 与 美股 T 日收益率 的 Pearson 相关",
            "pearson": pearson(pairs["cn_ret"], pairs["us_ret"]),
            "sample_days": len(pairs),
        }
    else:
        lead_lag = {"applicable": False, "description": "同一市场，不计算领先滞后"}

    return {
        "days_requested": days,
        "a": side(a_info, a_close),
        "b": side(b_info, b_close),
        "aligned": {
            "sample_days": len(aligned),
            "return_days": len(ret),
            "first_date": aligned.index[0] if len(aligned) else None,
            "last_date": aligned.index[-1] if len(aligned) else None,
        },
        "correlation": {
            "pearson": pearson(ret["a"], ret["b"]),
            "spearman": spearman(ret["a"], ret["b"]),
        },
        "rolling": {
            "dates": list(ret.index),
            "w20": rolling_corr(ret, 20),
            "w60": rolling_corr(ret, 60),
        },
        "lead_lag": lead_lag,
        "benchmark": {
            "a": {"index_name": a_info["index_name"], **benchmark_corr(a_close, close_series(a_index))},
            "b": {"index_name": b_info["index_name"], **benchmark_corr(b_close, close_series(b_index))},
        },
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def collect_stats(a: dict, b: dict, days: int = 120) -> dict:
    """a / b: {symbol, market}。拉取日 K 与大盘后计算。"""
    infos, klines, indexes = [], [], []
    for x in (a, b):
        adapter = get_adapter(x["market"])
        infos.append({
            "symbol": x["symbol"],
            "market": adapter.market,
            "name": adapter.name_of(x["symbol"]) or x["symbol"],
            "index_name": adapter.index_name,
        })
        klines.append(adapter.kline(x["symbol"], days))
        indexes.append(adapter.index_kline(days))
    return compute_stats(infos[0], klines[0], indexes[0], infos[1], klines[1], indexes[1], days)
