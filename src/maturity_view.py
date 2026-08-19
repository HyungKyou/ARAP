"""F1. 만기월별 AR/AP 그래프용 집계 (PRD §5 F1).

당월 포함 향후 6개월은 개별 월로, 그 이후는 "6개월 이후"로 묶는다.
실제 샘플 데이터에는 보고기준일보다 이미 지난 만기(연체, PRD §4.1.3)도 다수 섞여 있어
PRD 원문에는 없는 "과거(연체)" 버킷을 추가했다 — 이걸 누락하면 연체 라인이 그래프에서
조용히 사라지게 된다.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

FORWARD_WINDOW_MONTHS = 6
OVERDUE_BUCKET = "과거(연체)"
BEYOND_WINDOW_BUCKET = "6개월 이후"


def _bucket_label(period: pd.Period, current: pd.Period, horizon: set[pd.Period]) -> str:
    if period < current:
        return OVERDUE_BUCKET
    if period in horizon:
        return str(period)
    return BEYOND_WINDOW_BUCKET


def build_maturity_buckets(df_with_usd: pd.DataFrame, report_date: date) -> pd.DataFrame:
    """만기월 버킷 × (AR, AP, Net) USD 합계 테이블. 행 순서는 시간순으로 고정."""
    df = df_with_usd.copy()
    df["만기월_기간"] = df["만기일"].dt.to_period("M")

    current = pd.Period(report_date, freq="M")
    horizon = [current + i for i in range(FORWARD_WINDOW_MONTHS)]
    horizon_set = set(horizon)

    df["버킷"] = df["만기월_기간"].apply(lambda p: _bucket_label(p, current, horizon_set))

    grouped = df.groupby(["버킷", "구분"])["USD환산금액"].sum().unstack(fill_value=0.0)
    for col in ("AR", "AP"):
        if col not in grouped.columns:
            grouped[col] = 0.0
    grouped["Net"] = grouped["AR"] - grouped["AP"]

    row_order = [OVERDUE_BUCKET] + [str(p) for p in horizon] + [BEYOND_WINDOW_BUCKET]
    grouped = grouped.reindex(row_order, fill_value=0.0)
    grouped = grouped[["AR", "AP", "Net"]]
    grouped.index.name = "만기월"
    return grouped.reset_index()
