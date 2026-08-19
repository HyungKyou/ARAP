"""F3. 예측환율 AI 수집 + 백분위 기반 4개 시나리오 산출 (PRD §4.3, §5 F3).

실시간 웹 수집(리서치 자료 크롤링/검색)은 이번 단계 범위 밖이다. 대신 `ForecastSource`
인터페이스로 분리해두어, 나중에 실제 수집기(WebSearch 기반 Agent 등)로 교체할 때
`compute_percentile_scenarios()` 이하 로직은 손댈 필요가 없도록 한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

import pandas as pd

from .pnl_engine import ScenarioInput

MIN_SAMPLES_FOR_PERCENTILE = 5

SCENARIO_LABELS = ("하위 10%(원화강세)", "중앙값", "상위 75%", "상위 90%(원화약세)")
QUARTER_LABELS = ("1Q", "2Q", "3Q", "4Q")


@dataclass(frozen=True)
class ForecastSample:
    institution: str      # 기관명 (예: "한국은행", "IMF")
    published_date: date  # 발표일
    citation: str         # 원문 링크 또는 인용 텍스트
    rate: float           # 당월 말 원/달러 전망치 — 시나리오(P10~P90) 산출에 쓰이는 값
    quarterly: dict[str, float] = field(default_factory=dict)  # 올해 분기별 {"1Q":..,"2Q":..,"3Q":..,"4Q":..}
    next_year_rate: float | None = None  # 내년도 전망치


class ForecastSource(Protocol):
    def fetch_samples(self, target_month: str) -> list[ForecastSample]: ...


class MockForecastSource:
    """v1 스텁 — 실제 기관 리서치 자료 대신 하드코딩된 표본을 반환한다.

    TODO(로드맵): 한국은행/IMF WEO/증권사 리서치센터 등 §4.3 원천을 실시간으로
    수집하는 Agent로 교체. 인터페이스(ForecastSource)만 지키면 이 클래스만 바뀌면 된다.
    """

    def __init__(self, samples: list[ForecastSample] | None = None) -> None:
        self._samples = samples or _DEFAULT_MOCK_SAMPLES

    def fetch_samples(self, target_month: str) -> list[ForecastSample]:
        return list(self._samples)


_DEFAULT_MOCK_SAMPLES = [
    ForecastSample(
        "한국은행", date(2026, 8, 1), "한국은행 경제전망보고서(2026.08)", 1360.0,
        quarterly={"1Q": 1320.0, "2Q": 1340.0, "3Q": 1355.0, "4Q": 1370.0}, next_year_rate=1350.0,
    ),
    ForecastSample(
        "IMF", date(2026, 7, 15), "IMF World Economic Outlook Update (2026.07)", 1345.0,
        quarterly={"1Q": 1310.0, "2Q": 1330.0, "3Q": 1345.0, "4Q": 1360.0}, next_year_rate=1330.0,
    ),
    ForecastSample(
        "KB증권 리서치센터", date(2026, 8, 5), "KB증권 환율 전망 (2026.08.05)", 1372.0,
        quarterly={"1Q": 1330.0, "2Q": 1350.0, "3Q": 1365.0, "4Q": 1385.0}, next_year_rate=1360.0,
    ),
    ForecastSample(
        "신한투자증권", date(2026, 8, 3), "신한투자증권 FX 위클리 (2026.08.03)", 1390.0,
        quarterly={"1Q": 1335.0, "2Q": 1360.0, "3Q": 1380.0, "4Q": 1400.0}, next_year_rate=1375.0,
    ),
    ForecastSample(
        "하나증권", date(2026, 8, 10), "하나증권 외환 전망 (2026.08.10)", 1405.0,
        quarterly={"1Q": 1340.0, "2Q": 1365.0, "3Q": 1390.0, "4Q": 1415.0}, next_year_rate=1390.0,
    ),
    ForecastSample(
        "Goldman Sachs", date(2026, 8, 2), "GS FX Strategy Note (2026.08.02)", 1350.0,
        quarterly={"1Q": 1315.0, "2Q": 1335.0, "3Q": 1350.0, "4Q": 1365.0}, next_year_rate=1340.0,
    ),
    ForecastSample(
        "JPMorgan", date(2026, 8, 6), "JPM Global FX Outlook (2026.08.06)", 1398.0,
        quarterly={"1Q": 1330.0, "2Q": 1355.0, "3Q": 1385.0, "4Q": 1405.0}, next_year_rate=1380.0,
    ),
    ForecastSample(
        "Nomura", date(2026, 7, 28), "Nomura Asia FX Monthly (2026.07.28)", 1415.0,
        quarterly={"1Q": 1345.0, "2Q": 1370.0, "3Q": 1400.0, "4Q": 1420.0}, next_year_rate=1395.0,
    ),
]


def compute_percentile_scenarios(
    samples: list[ForecastSample],
) -> tuple[list[ScenarioInput], list[str]]:
    """표본으로부터 4개 시나리오(P10/P50/P75/P90)를 산출한다.

    표본 < 5개면 백분위 대신 최소/중앙/최대 기반 대체 산식을 쓰고 경고 문구를 반환한다
    (PRD §5 F3 — 대체 산식의 정확한 형태는 §11 확인 필요 항목으로 남아 있어 v1 임시 정의).
    """
    warnings: list[str] = []
    rates = pd.Series([s.rate for s in samples], dtype=float)

    if len(rates) < MIN_SAMPLES_FOR_PERCENTILE:
        warnings.append(
            f"예측환율 표본 수({len(rates)}건)가 {MIN_SAMPLES_FOR_PERCENTILE}건 미만이라 "
            "백분위수 대신 최소/중앙/최대 기반 대체 산식을 적용했습니다 (PRD §11 확인 필요)."
        )
        lo, med, hi = rates.min(), rates.median(), rates.max()
        values = {
            "하위 10%(원화강세)": lo,
            "중앙값": med,
            "상위 75%": (med + hi) / 2,
            "상위 90%(원화약세)": hi,
        }
    else:
        values = {
            "하위 10%(원화강세)": rates.quantile(0.10),
            "중앙값": rates.quantile(0.50),
            "상위 75%": rates.quantile(0.75),
            "상위 90%(원화약세)": rates.quantile(0.90),
        }

    source_desc = f"AI 수집 ({len(samples)}개 기관 표본 기반)"
    scenarios = [
        ScenarioInput(label=label, rate=float(values[label]), source=source_desc, is_base=(label == "중앙값"))
        for label in SCENARIO_LABELS
    ]
    return scenarios, warnings


def samples_to_dataframe(samples: list[ForecastSample]) -> pd.DataFrame:
    """리포트 부록(F5)의 예측환율 출처 로그 표(간단 버전: 당월말 전망치만)."""
    return pd.DataFrame(
        [
            {"기관명": s.institution, "발표일": s.published_date, "출처": s.citation, "전망치": s.rate}
            for s in samples
        ]
    )


def samples_to_horizon_dataframe(samples: list[ForecastSample], report_date: date) -> pd.DataFrame:
    """2번 페이지(환율예측치)용 — 기관별 당월말/올해 분기별/내년도 전망치를 한 표로.

    분기·내년도 수치 자체는 목업(고정값)이라 report_date를 바꿔도 값은 그대로다 — 라벨(연도)만
    report_date 기준으로 갱신된다. 실제 수집기로 교체될 때 이 표의 컬럼 구조는 그대로 두고
    ForecastSample 생성 쪽만 바뀌면 되도록 설계했다.
    """
    month_label = f"{report_date:%Y-%m} 말"
    year = report_date.year
    rows = []
    for s in samples:
        row = {"기관명": s.institution, "발표일": s.published_date, month_label: s.rate}
        for q in QUARTER_LABELS:
            row[f"{year} {q}"] = s.quarterly.get(q)
        row[f"{year + 1}년(내년도)"] = s.next_year_rate
        row["출처"] = s.citation
        rows.append(row)
    return pd.DataFrame(rows)
