"""환율 변환 및 가중평균 기표환율 계산 엔진 (PRD §6.1, §6.2).

⚠️ 이력 있는 결함 (PRD §6.1 "v1.1 수정" 참조):
    최초 설계는 통화 구분 없이 `원화금액 ÷ 당일 USD/KRW 스팟환율`을 모든 라인에 적용했다.
    이 방식은 대수적으로 아래 항등식을 만족시켜버려서 §6.2의 가중평균 기표환율이
    "통화와 무관하게 항상 당일 USD/KRW 스팟환율"이라는 상수로 붕괴한다:

        원화금액 / USD환산금액
      = 원화금액 / (원화금액 / USD스팟)
      = USD스팟   (통화가 무엇이든 동일)

    즉 지표 자체가 무의미해진다. 이 모듈을 수정할 때는 반드시
    `weighted_avg_booking_rate()`가 통화 구성이 다른 포트폴리오에 대해
    서로 다른 값을 내는지 확인할 것 (전부 USD/KRW 스팟과 같은 값이 나오면 결함 재발).

아래 (신) 산식만 사용한다:
    USD 라인      : USD환산금액 = 외화금액
    USD 외 라인   : USD환산금액 = 외화금액 × (해당통화/KRW 스팟) ÷ (USD/KRW 스팟)
"""
from __future__ import annotations

from typing import Protocol

import pandas as pd

# 당일 스팟환율 스텁 (KRW per 1 unit). 실제 서비스에서는 한국은행/서울외국환중개 등
# 고시환율 API로 교체될 자리 — SpotRateSource 인터페이스만 지키면 교체 가능하다.
DEFAULT_SPOT_RATES: dict[str, float] = {
    "USD": 1380.0,
    "EUR": 1500.0,
    "JPY": 9.2,   # 원/1엔 (100엔 단위 아님 — PRD §4.1.3 확인 사항)
    "CNY": 190.0,
}


class SpotRateSource(Protocol):
    def get_rates(self) -> dict[str, float]: ...


class StaticSpotRateSource:
    """v1 스텁 구현체. 고정 딕셔너리를 그대로 반환한다."""

    def __init__(self, rates: dict[str, float] | None = None) -> None:
        self._rates = dict(rates or DEFAULT_SPOT_RATES)

    def get_rates(self) -> dict[str, float]:
        return dict(self._rates)


def add_usd_amount(df: pd.DataFrame, spot_rates: dict[str, float]) -> pd.DataFrame:
    """라인별 USD환산금액 컬럼을 추가한다 (§6.1 신 산식).

    스팟환율이 없거나(키 없음) 0 이하(사이드바가 모르는 통화에 기본값 0.0을 채운 경우 포함)면
    변환 불가로 보고 NaN을 반환한다 — 0을 그대로 곱하면 "변환 안 됨"이 "USD환산금액 0원"으로
    둔갑해 weighted_avg_booking_rate()의 분자/분모를 비대칭적으로 오염시킨다 (검증된 버그, §6.2 참조).
    """

    usd_spot = spot_rates.get("USD")

    def _convert(row: pd.Series) -> float:
        if row["통화"] == "USD":
            return row["외화금액"]
        spot = spot_rates.get(row["통화"])
        if not spot or not usd_spot or spot <= 0 or usd_spot <= 0:
            return float("nan")
        return row["외화금액"] * spot / usd_spot

    out = df.copy()
    out["USD환산금액"] = out.apply(_convert, axis=1)
    return out


def add_maturity_month(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["만기월"] = out["만기일"].dt.to_period("M").astype(str)
    return out


def weighted_avg_booking_rate(df: pd.DataFrame) -> float:
    """금액가중평균 기표환율 (§6.2) = Σ원화금액 ÷ ΣUSD환산금액.

    ⚠️ 검증된 버그(수정됨): USD환산금액이 NaN인 라인(변환 불가 통화)이 섞여 있으면
    pandas Series.sum()이 기본적으로 NaN을 건너뛰므로, 분자(원화금액 합)는 그 라인의
    실제 금액을 포함하는데 분모(USD환산금액 합)는 그 라인을 빼버려 비율이 터무니없이
    왜곡된다 (실측: 정상 포트폴리오에 변환 불가 라인 하나만 섞여도 기표환율이 10배 이상
    벌어짐). 반드시 두 합계를 "USD환산금액이 유효한 라인"이라는 동일한 부분집합에서
    계산해야 한다 — 이 필터를 지우면 결함이 재발한다.
    """
    convertible = df[df["USD환산금액"].notna()]
    total_krw = convertible["원화금액"].sum()
    total_usd = convertible["USD환산금액"].sum()
    if not total_usd:
        return float("nan")
    return total_krw / total_usd


def booking_rate_overview(df_with_usd: pd.DataFrame) -> dict[str, float]:
    """AR/AP 전체 가중평균 기표환율 (§6.2)."""
    result = {}
    for gubun in ("AR", "AP"):
        subset = df_with_usd[df_with_usd["구분"] == gubun]
        result[gubun] = weighted_avg_booking_rate(subset) if len(subset) else float("nan")
    return result


def booking_rate_by_month(df_with_usd: pd.DataFrame) -> pd.DataFrame:
    """만기월별 AR/AP 가중평균 기표환율 브레이크다운 (§6.2 하단 breakdown 요구사항)."""
    df = add_maturity_month(df_with_usd)
    rows = []
    for (gubun, month), group in df.groupby(["구분", "만기월"]):
        rows.append(
            {
                "구분": gubun,
                "만기월": month,
                "라인수": len(group),
                "기표환율": weighted_avg_booking_rate(group),
            }
        )
    return pd.DataFrame(rows).sort_values(["만기월", "구분"]).reset_index(drop=True)
