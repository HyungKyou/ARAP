"""F1 만기월 버킷팅 검증 — 과거(연체)/6개월 윈도우/6개월 이후 분류가 라인을 누락하지 않는지."""
from datetime import date

import pandas as pd

from src.maturity_view import (
    BEYOND_WINDOW_BUCKET,
    OVERDUE_BUCKET,
    build_maturity_buckets,
)

REPORT_DATE = date(2026, 8, 19)  # 당월 = 2026-08


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_buckets_cover_overdue_current_and_beyond_without_dropping_lines():
    df = _df(
        [
            {"구분": "AR", "만기일": pd.Timestamp("2025-01-15"), "USD환산금액": 100.0},  # 과거(연체)
            {"구분": "AR", "만기일": pd.Timestamp("2026-08-20"), "USD환산금액": 200.0},  # 당월
            {"구분": "AP", "만기일": pd.Timestamp("2027-06-01"), "USD환산금액": 50.0},   # 6개월 이후
        ]
    )
    result = build_maturity_buckets(df, REPORT_DATE)

    assert result["AR"].sum() + result["AP"].sum() == 100.0 + 200.0 + 50.0  # 라인 유실 없음

    overdue_row = result[result["만기월"] == OVERDUE_BUCKET].iloc[0]
    assert overdue_row["AR"] == 100.0

    current_row = result[result["만기월"] == "2026-08"].iloc[0]
    assert current_row["AR"] == 200.0

    beyond_row = result[result["만기월"] == BEYOND_WINDOW_BUCKET].iloc[0]
    assert beyond_row["AP"] == 50.0


def test_row_order_is_chronological():
    df = _df([{"구분": "AR", "만기일": pd.Timestamp("2026-08-19"), "USD환산금액": 1.0}])
    result = build_maturity_buckets(df, REPORT_DATE)
    expected_order = [OVERDUE_BUCKET, "2026-08", "2026-09", "2026-10", "2026-11", "2026-12", "2027-01", BEYOND_WINDOW_BUCKET]
    assert list(result["만기월"]) == expected_order


def test_net_is_ar_minus_ap():
    df = _df(
        [
            {"구분": "AR", "만기일": pd.Timestamp("2026-08-19"), "USD환산금액": 300.0},
            {"구분": "AP", "만기일": pd.Timestamp("2026-08-19"), "USD환산금액": 120.0},
        ]
    )
    result = build_maturity_buckets(df, REPORT_DATE)
    row = result[result["만기월"] == "2026-08"].iloc[0]
    assert row["Net"] == 180.0
