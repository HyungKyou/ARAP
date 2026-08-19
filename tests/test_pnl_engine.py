"""§6.3 시나리오별 환차·환산손익 계산 검증 (F4)."""
from datetime import date

import pandas as pd
import pytest

from src.pnl_engine import (
    ScenarioInput,
    build_pnl_matrix,
    classify_realized,
    compute_line_pnl,
    month_end,
    line_booking_rate_usd_basis,
)

REPORT_DATE = date(2026, 8, 19)


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_month_end():
    assert month_end(REPORT_DATE) == pd.Timestamp("2026-08-31")


def test_line_booking_rate_usd_basis_matches_original_rate_for_usd_line():
    df = _df([{"원화금액": 1_300_000.0, "USD환산금액": 1000.0}])
    rate = line_booking_rate_usd_basis(df)
    assert rate.iloc[0] == pytest.approx(1300.0)


def test_compute_line_pnl_ar_gains_when_rate_rises():
    df = _df([{"구분": "AR", "원화금액": 1_300_000.0, "USD환산금액": 1000.0}])
    pnl = compute_line_pnl(df, rate=1350.0)
    assert pnl.iloc[0] == pytest.approx((1350.0 - 1300.0) * 1000.0)


def test_compute_line_pnl_ap_loses_when_rate_rises():
    df = _df([{"구분": "AP", "원화금액": 1_300_000.0, "USD환산금액": 1000.0}])
    pnl = compute_line_pnl(df, rate=1350.0)
    assert pnl.iloc[0] == pytest.approx((1300.0 - 1350.0) * 1000.0)


def test_classify_realized_boundary_is_inclusive():
    df = _df(
        [
            {"만기일": pd.Timestamp("2026-08-31")},  # 당월 말과 정확히 같음 → 환차손익(실현)
            {"만기일": pd.Timestamp("2026-09-01")},  # 하루 뒤 → 환산손익(미실현)
        ]
    )
    realized = classify_realized(df, REPORT_DATE)
    assert realized.iloc[0] is True or bool(realized.iloc[0])
    assert not bool(realized.iloc[1])


def test_build_pnl_matrix_natural_hedge_offsets_to_zero_net():
    df = _df(
        [
            {  # AR: 만기 당월 내 → 환차손익
                "구분": "AR", "만기일": pd.Timestamp("2026-07-01"),
                "원화금액": 1_300_000.0, "USD환산금액": 1000.0,
            },
            {  # AP: 만기 당월 이후 → 환산손익, 같은 기표환율/금액이라 순손익은 상쇄
                "구분": "AP", "만기일": pd.Timestamp("2026-10-01"),
                "원화금액": 1_300_000.0, "USD환산금액": 1000.0,
            },
        ]
    )
    scenarios = [ScenarioInput(label="중앙값", rate=1350.0, source="test", is_base=True)]
    matrix = build_pnl_matrix(df, scenarios, REPORT_DATE)

    def amount(gubun, kind):
        row = matrix[(matrix["구분"] == gubun) & (matrix["손익유형"] == kind)]
        return row["금액"].iloc[0]

    assert amount("AR", "환차손익") == pytest.approx(50_000.0)
    assert amount("AR", "환산손익") == pytest.approx(0.0)
    assert amount("AP", "환산손익") == pytest.approx(-50_000.0)
    assert amount("AP", "환차손익") == pytest.approx(0.0)
    assert amount("Net", "합계") == pytest.approx(0.0)  # 자연헤지


def test_build_pnl_matrix_delta_vs_base():
    df = _df(
        [
            {"구분": "AR", "만기일": pd.Timestamp("2026-07-01"), "원화금액": 1_300_000.0, "USD환산금액": 1000.0},
        ]
    )
    scenarios = [
        ScenarioInput(label="중앙값", rate=1350.0, source="test", is_base=True),
        ScenarioInput(label="상위 90%(원화약세)", rate=1400.0, source="test", is_base=False),
    ]
    matrix = build_pnl_matrix(df, scenarios, REPORT_DATE)

    base_row = matrix[(matrix["시나리오"] == "중앙값") & (matrix["구분"] == "AR") & (matrix["손익유형"] == "합계")]
    other_row = matrix[
        (matrix["시나리오"] == "상위 90%(원화약세)") & (matrix["구분"] == "AR") & (matrix["손익유형"] == "합계")
    ]

    assert base_row["Base대비Delta"].iloc[0] == pytest.approx(0.0)
    expected_delta = (1400.0 - 1300.0) * 1000.0 - (1350.0 - 1300.0) * 1000.0
    assert other_row["Base대비Delta"].iloc[0] == pytest.approx(expected_delta)
