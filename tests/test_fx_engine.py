"""§6.1 USD 환산 / §6.2 가중평균 기표환율 계산 검증.

가장 중요한 테스트는 `test_no_regression_to_v1_bug` 다 — PRD §6.1에 기록된
"구 산식이 가중평균 기표환율을 통화와 무관하게 항상 당일 USD/KRW 스팟환율로
붕괴시키는" 결함이 재발하지 않았는지를 확인한다.
"""
from pathlib import Path

import pandas as pd
import pytest

from src.fx_engine import (
    DEFAULT_SPOT_RATES,
    StaticSpotRateSource,
    add_usd_amount,
    booking_rate_overview,
    weighted_avg_booking_rate,
)
from src.ingest import load_ar

ROOT = Path(__file__).resolve().parent.parent
AR_PATH = ROOT / "실습AR_300건.xlsx"

SPOT = {"USD": 1380.0, "EUR": 1500.0, "JPY": 9.2, "CNY": 190.0}


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_usd_line_passes_through_unchanged():
    df = _df([{"통화": "USD", "외화금액": 1000.0}])
    out = add_usd_amount(df, SPOT)
    assert out.loc[0, "USD환산금액"] == 1000.0


def test_non_usd_line_uses_cross_rate_not_krw_over_usd_spot():
    df = _df([{"통화": "EUR", "외화금액": 1000.0}])
    out = add_usd_amount(df, SPOT)
    expected = 1000.0 * SPOT["EUR"] / SPOT["USD"]
    assert out.loc[0, "USD환산금액"] == pytest.approx(expected)


def test_unknown_currency_yields_nan_not_crash():
    df = _df([{"통화": "GBP", "외화금액": 1000.0}])
    out = add_usd_amount(df, SPOT)
    assert pd.isna(out.loc[0, "USD환산금액"])


def test_no_regression_to_v1_bug():
    """단일 EUR 라인(USD 라인 전혀 없음)의 가중평균 기표환율은
    §6.1(신) 산식으로 손으로 계산 가능한 값(1334.0)이 나와야 하며,
    구 산식이 항상 반환하던 '당일 USD/KRW 스팟환율(1380.0)'과 달라야 한다.

    손계산: 라인 적용환율 = 1,450,000 / 1000 = 1450 (EUR)
            USD환산금액   = 1000 × 1500 / 1380 = 1086.9565...
            가중평균 기표환율 = 1,450,000 / 1086.9565... = 1450 × 1380 / 1500 = 1334.0
    """
    df = _df([{"구분": "AR", "통화": "EUR", "외화금액": 1000.0, "원화금액": 1_450_000.0}])
    with_usd = add_usd_amount(df, SPOT)
    rate = weighted_avg_booking_rate(with_usd)

    assert rate == pytest.approx(1334.0)
    assert rate != pytest.approx(SPOT["USD"])  # 구 산식이라면 여기서 1380.0이 나왔을 것


def test_mixed_currency_portfolio_produces_different_rates_per_side():
    """서로 다른 통화 구성의 AR/AP는 서로 다른 가중평균 기표환율을 내야 한다
    (전부 동일한 값이 나오면 §6.1 구 산식으로 회귀한 것)."""
    df = _df(
        [
            {"구분": "AR", "통화": "EUR", "외화금액": 1000.0, "원화금액": 1_450_000.0},
            {"구분": "AP", "통화": "JPY", "외화금액": 100_000.0, "원화금액": 900_000.0},
        ]
    )
    with_usd = add_usd_amount(df, SPOT)
    overview = booking_rate_overview(with_usd)

    assert overview["AR"] != pytest.approx(overview["AP"])
    assert overview["AR"] != pytest.approx(SPOT["USD"])
    assert overview["AP"] != pytest.approx(SPOT["USD"])


def test_static_spot_rate_source_returns_default_rates():
    source = StaticSpotRateSource()
    assert source.get_rates() == DEFAULT_SPOT_RATES
    # 반환값을 수정해도 내부 상태에 영향 없어야 함 (매 호출 시 방어적 복사)
    rates = source.get_rates()
    rates["USD"] = 0.0
    assert source.get_rates()["USD"] == DEFAULT_SPOT_RATES["USD"]


def test_unconvertible_currency_line_does_not_contaminate_weighted_avg_rate():
    """4단계 검토에서 발견된 버그(수정됨): USD환산금액이 NaN인 라인이 섞이면
    분자(원화금액 합)는 그 라인을 포함하는데 분모(USD환산금액 합)는 pandas의 기본
    skipna 동작 때문에 빠져서 비율이 터무니없이 왜곡됐었다 (1380 → 11380로 폭증 실측).
    변환 가능한 라인만으로 계산한 값과 정확히 같아야 한다.
    """
    convertible = _df([{"구분": "AR", "통화": "USD", "외화금액": 1000.0, "원화금액": 1_380_000.0}])
    with_gbp = _df(
        [
            {"구분": "AR", "통화": "USD", "외화금액": 1000.0, "원화금액": 1_380_000.0},
            {"구분": "AR", "통화": "GBP", "외화금액": 5000.0, "원화금액": 10_000_000.0},  # SPOT에 없음
        ]
    )
    rate_without_bad_line = weighted_avg_booking_rate(add_usd_amount(convertible, SPOT))
    rate_with_bad_line = weighted_avg_booking_rate(add_usd_amount(with_gbp, SPOT))

    assert rate_with_bad_line == pytest.approx(rate_without_bad_line)
    assert rate_with_bad_line == pytest.approx(1380.0)


def test_zero_spot_rate_treated_same_as_missing_not_as_free_conversion():
    """사이드바가 원장에 있는 모든 통화에 스팟환율 입력창을 만들어주지만, 담당자가
    새 통화의 값을 0으로 남겨둘 수 있다. 0을 진짜 환율처럼 곱하면 위와 같은
    분자/분모 불일치가 '키 없음'이 아니라 '0으로 방치'라는 경로로도 재발한다."""
    df = _df([{"구분": "AR", "통화": "XYZ", "외화금액": 1000.0, "원화금액": 1_000_000.0}])
    spot_with_zero_default = {**SPOT, "XYZ": 0.0}
    out = add_usd_amount(df, spot_with_zero_default)
    assert pd.isna(out.loc[0, "USD환산금액"])


def test_manual_verification_against_real_sample_line():
    """1단계 완료 기준: 실제 샘플 파일 라인 하나를 골라 파이프라인 전체 배선(컬럼 매핑 →
    적용환율 역산 → USD 환산)이 깨지지 않았는지 확인한다."""
    ar = load_ar(str(AR_PATH))
    row = ar.iloc[0]  # EUR, 외화금액 157512.98, 원화금액 224806131 (엑셀에서 직접 확인한 값)

    expected_rate = row["원화금액"] / row["외화금액"]
    expected_usd = row["외화금액"] * DEFAULT_SPOT_RATES["EUR"] / DEFAULT_SPOT_RATES["USD"]

    one_row_df = ar.iloc[[0]].copy()
    one_row_df["적용환율"] = one_row_df["원화금액"] / one_row_df["외화금액"]
    with_usd = add_usd_amount(one_row_df, DEFAULT_SPOT_RATES)

    assert with_usd.loc[0, "적용환율"] == pytest.approx(expected_rate)
    assert with_usd.loc[0, "USD환산금액"] == pytest.approx(expected_usd)
