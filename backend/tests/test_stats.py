import pandas as pd
import pytest

from app.analysis.stats import (
    align_closes,
    close_series,
    compute_stats,
    lead_lag_pairs,
    returns,
    spearman,
)


def kline(rows: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"date": d, "open": c, "high": c, "low": c, "close": c, "volume": 1} for d, c in rows.items()]
    )


def series(rows: dict[str, float]) -> pd.Series:
    return close_series(kline(rows))


# ---- 日期对齐 ----

def test_align_keeps_only_common_dates():
    # CN 10-01 国庆休市；US 10-03 无交易（假设）
    cn = series({"2026-09-30": 10, "2026-10-02": 11, "2026-10-05": 12})
    us = series({"2026-09-30": 100, "2026-10-01": 101, "2026-10-02": 102, "2026-10-05": 103})
    aligned = align_closes(cn, us)
    assert list(aligned.index) == ["2026-09-30", "2026-10-02", "2026-10-05"]
    assert aligned.loc["2026-10-02"].tolist() == [11, 102]


def test_align_sorts_and_dedups_unsorted_input():
    df = kline({"2026-10-05": 3, "2026-10-01": 1, "2026-10-02": 2})
    df = pd.concat([df, kline({"2026-10-02": 2.5})], ignore_index=True)
    s = close_series(df)
    assert list(s.index) == ["2026-10-01", "2026-10-02", "2026-10-05"]
    assert s["2026-10-02"] == 2.5


def test_align_no_overlap_is_empty():
    aligned = align_closes(series({"2026-01-01": 1}), series({"2026-01-02": 1}))
    assert aligned.empty


def test_returns_computed_after_alignment():
    # US 10-01 被丢弃，所以 US 在 10-02 的收益是相对 09-30 的
    cn = series({"2026-09-30": 10, "2026-10-02": 11})
    us = series({"2026-09-30": 100, "2026-10-01": 50, "2026-10-02": 110})
    ret = returns(align_closes(cn, us))
    assert list(ret.index) == ["2026-10-02"]
    assert ret.loc["2026-10-02", "a"] == pytest.approx(0.1)
    assert ret.loc["2026-10-02", "b"] == pytest.approx(0.1)


def test_sample_days_reported_in_stats():
    cn = kline({"2026-09-29": 10, "2026-09-30": 11, "2026-10-08": 12, "2026-10-09": 11})
    us = kline({"2026-09-29": 1, "2026-09-30": 2, "2026-10-01": 3, "2026-10-02": 4, "2026-10-09": 3})
    info_cn = {"symbol": "X", "market": "CN", "name": "X", "index_name": "沪深300"}
    info_us = {"symbol": "Y", "market": "US", "name": "Y", "index_name": "纳斯达克100"}
    out = compute_stats(info_cn, cn, cn, info_us, us, us, 120)
    assert out["a"]["raw_days"] == 4
    assert out["b"]["raw_days"] == 5
    assert out["aligned"]["sample_days"] == 3  # 09-29, 09-30, 10-09
    assert out["aligned"]["return_days"] == 2
    assert out["rolling"]["dates"] == ["2026-09-30", "2026-10-09"]
    assert out["benchmark"]["a"]["pearson"] == 1.0  # 与自身对照


# ---- 领先滞后配对 ----

def test_lead_lag_pairs_next_cn_day():
    us = series({"2026-10-05": 100, "2026-10-06": 110, "2026-10-07": 99})
    cn = series({"2026-10-06": 10, "2026-10-07": 11, "2026-10-08": 12})
    pairs = lead_lag_pairs(cn, us)
    # US 10-06 的收益 → CN 10-07；US 10-07 → CN 10-08
    assert pairs[["us_date", "cn_date"]].values.tolist() == [
        ["2026-10-06", "2026-10-07"],
        ["2026-10-07", "2026-10-08"],
    ]


def test_lead_lag_cn_holiday_keeps_latest_us_day():
    # CN 10-01 ~ 10-07 休市，期间多个 US 交易日都映射到 CN 10-08，只保留 US 10-07
    us = series({"2026-09-29": 1, "2026-09-30": 2, "2026-10-01": 3, "2026-10-02": 4, "2026-10-07": 5})
    cn = series({"2026-09-29": 10, "2026-09-30": 11, "2026-10-08": 12})
    pairs = lead_lag_pairs(cn, us)
    assert pairs[["us_date", "cn_date"]].values.tolist() == [["2026-10-07", "2026-10-08"]]
    assert pairs["us_ret"].iloc[0] == pytest.approx(5 / 4 - 1)


def test_lead_lag_same_market_not_applicable():
    k = kline({"2026-10-01": 1, "2026-10-02": 2, "2026-10-05": 3})
    info = {"symbol": "X", "market": "CN", "name": "X", "index_name": "沪深300"}
    out = compute_stats(info, k, k, info, k, k, 120)
    assert out["lead_lag"]["applicable"] is False


# ---- 相关系数 ----

def test_spearman_monotonic_is_one():
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    y = x**3
    assert spearman(x, y) == 1.0
