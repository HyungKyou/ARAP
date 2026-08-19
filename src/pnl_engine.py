"""예측환율 시나리오별 환차·환산손익 계산 (PRD §6.3, F4).

AI 시나리오(F3)와 수동 입력(F3-2)은 결과물이 다를 뿐 계산 방식은 동일하므로,
둘 다 `ScenarioInput`으로 통일해 이 모듈 하나로 처리한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class ScenarioInput:
    label: str          # 예: "중앙값", "수동입력1"
    rate: float          # 원/달러 예측환율
    source: str          # 예: "AI 수집(8개 표본)", "수동 입력(홍길동, 2026-08-19 10:00)"
    is_base: bool = False  # Base(중앙값) 시나리오 여부 — Delta 계산 기준


def month_end(report_date: date) -> pd.Timestamp:
    """보고기준일이 속한 달의 말일 (§6.3 "당월 말")."""
    return pd.Timestamp(report_date) + pd.offsets.MonthEnd(0)


def line_booking_rate_usd_basis(df_with_usd: pd.DataFrame) -> pd.Series:
    """라인별 기표환율(USD환산 기준) = 원화금액 ÷ USD환산금액 (§6.4).

    USD 라인은 원래의 적용환율과 정확히 일치하고, 비USD 라인은 교차환산이 반영된 값이다.
    """
    return df_with_usd["원화금액"] / df_with_usd["USD환산금액"]


def compute_line_pnl(df_with_usd: pd.DataFrame, rate: float) -> pd.Series:
    """§6.3 라인별 손익.

    AR: (예측환율 − 기표환율_라인) × USD환산금액
    AP: (기표환율_라인 − 예측환율) × USD환산금액
    """
    line_rate = line_booking_rate_usd_basis(df_with_usd)
    is_ar = df_with_usd["구분"] == "AR"
    pnl = pd.Series(0.0, index=df_with_usd.index)
    pnl.loc[is_ar] = (rate - line_rate.loc[is_ar]) * df_with_usd.loc[is_ar, "USD환산금액"]
    pnl.loc[~is_ar] = (line_rate.loc[~is_ar] - rate) * df_with_usd.loc[~is_ar, "USD환산금액"]
    return pnl


def classify_realized(df_with_usd: pd.DataFrame, report_date: date) -> pd.Series:
    """만기일 ≤ 당월 말 → 환차손익(실현), 그 외 → 환산손익(미실현) (§6.3)."""
    cutoff = month_end(report_date)
    return df_with_usd["만기일"] <= cutoff


def build_pnl_matrix(
    df_with_usd: pd.DataFrame,
    scenarios: list[ScenarioInput],
    report_date: date,
) -> pd.DataFrame:
    """(시나리오) × (환산손익/환차손익/합계) × (AR/AP/Net) 매트릭스를 long-form으로 반환.

    컬럼: 시나리오, 출처, 환율, 구분, 손익유형, 금액, Base대비Delta
    """
    realized = classify_realized(df_with_usd, report_date)
    kind_of_row = realized.map({True: "환차손익", False: "환산손익"})

    rows: list[dict] = []
    for sc in scenarios:
        pnl = compute_line_pnl(df_with_usd, sc.rate)
        tmp = pd.DataFrame(
            {"구분": df_with_usd["구분"].values, "손익유형": kind_of_row.values, "손익": pnl.values}
        )

        for gubun in ("AR", "AP", "Net"):
            subset = tmp if gubun == "Net" else tmp[tmp["구분"] == gubun]
            for kind in ("환차손익", "환산손익"):
                amount = subset.loc[subset["손익유형"] == kind, "손익"].sum()
                rows.append(
                    {
                        "시나리오": sc.label, "출처": sc.source, "환율": sc.rate,
                        "구분": gubun, "손익유형": kind, "금액": amount,
                    }
                )
            rows.append(
                {
                    "시나리오": sc.label, "출처": sc.source, "환율": sc.rate,
                    "구분": gubun, "손익유형": "합계", "금액": subset["손익"].sum(),
                }
            )

    matrix = pd.DataFrame(rows)

    base_labels = [sc.label for sc in scenarios if sc.is_base]
    if base_labels:
        base_label = base_labels[0]
        base_values = matrix[matrix["시나리오"] == base_label].set_index(["구분", "손익유형"])["금액"]
        matrix["Base대비Delta"] = matrix.apply(
            lambda r: r["금액"] - base_values.get((r["구분"], r["손익유형"]), float("nan")), axis=1
        )
    else:
        matrix["Base대비Delta"] = float("nan")

    return matrix
