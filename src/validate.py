"""AR/AP 원장 검증·정제 규칙 (PRD §4.1.3, 7개 규칙 전부 구현).

ingest.load_ledger()가 만든 표준 스키마 DataFrame을 받아:
  1) 격리(quarantine)  — 계산 자체가 불가능하거나 명백히 오류인 라인 (전체 리포트에서 제외 + 알림)
  2) 제외(exclude)     — 정상 데이터이지만 이번 리포트 집계 대상이 아닌 라인 (AP 기결제 건)
  3) 플래그(flag)       — 집계에는 포함하되 주의가 필요함을 표시 (연체/네고/스팟환율 괴리)
로 분류하고, 살아남은 라인에는 적용환율을 역산해 붙인다.

규칙 우선순위(§4.1.3 1~3번은 배타적 격리 사유이므로 먼저 걸러내고, 이후 4~7번은 남은 라인에 적용):
  1. 외화금액/원화금액 0 또는 결측 → 격리 ("금액결측또는0")
  2. 날짜 포맷 오류(YYYY.MM.DD 미준수, ingest 단계에서 이미 NaT로 변환됨) → 격리 ("날짜형식오류")
  3. 만기일 < 전기일 → 격리 ("만기일선행오류")
  4. 적용환율이 당일 스팟환율 대비 ±30% 이상 괴리 → 경고 플래그 (격리하지 않음)
  5. AP 반제일 존재 → 제외 ("반제완료")
  6. 만기일 < 보고기준일 → 연체 플래그
  7. AR 네고여부='Y' → 네고 플래그 (v1 기본값: 포함 + 표시, §11 확인 필요)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

SPOT_DEVIATION_THRESHOLD = 0.30


@dataclass
class ValidationResult:
    clean: pd.DataFrame                 # 집계 대상 (적용환율/플래그 컬럼 포함)
    quarantined: pd.DataFrame           # 격리된 라인 (격리사유 컬럼 포함)
    excluded_settled: pd.DataFrame      # AP 기결제 라인 (집계에서는 빠지지만 오류는 아님)
    summary: dict = field(default_factory=dict)


def validate_and_enrich(
    ledger: pd.DataFrame,
    spot_rates: dict[str, float],
    report_date: date,
) -> ValidationResult:
    df = ledger.copy()
    df["격리사유"] = None

    # --- 규칙 1: 금액 0/결측 ---
    bad_amount = (
        df["외화금액"].isna()
        | df["원화금액"].isna()
        | (df["외화금액"] == 0)
        | (df["원화금액"] == 0)
    )
    df.loc[bad_amount, "격리사유"] = "금액결측또는0"

    # --- 규칙 2: 날짜 포맷 오류 (ingest에서 파싱 실패 시 이미 NaT) ---
    bad_date = df["전기일"].isna() | df["만기일"].isna()
    df.loc[bad_date & df["격리사유"].isna(), "격리사유"] = "날짜형식오류"

    # --- 규칙 3: 만기일 < 전기일 ---
    # (bad_date로 격리된 라인은 비교 불가하므로 이미 격리사유가 채워진 라인은 건너뜀)
    comparable = df["격리사유"].isna()
    maturity_before_posting = comparable & (df["만기일"] < df["전기일"])
    df.loc[maturity_before_posting, "격리사유"] = "만기일선행오류"

    quarantined = df[df["격리사유"].notna()].copy()
    survivors = df[df["격리사유"].isna()].copy()

    # --- 규칙 5: AP 반제일 존재 → 제외 (오류 아님, 정상적으로 이미 결제된 건) ---
    settled_mask = survivors["반제일"].notna()
    excluded_settled = survivors[settled_mask].copy()
    excluded_settled["제외사유"] = "반제완료"
    clean = survivors[~settled_mask].copy()

    # --- 적용환율 역산 (원본에 환율 컬럼이 없어 라인 단위로 역산, PRD §4.1.3) ---
    clean["적용환율"] = clean["원화금액"] / clean["외화금액"]

    # --- 규칙 4: 스팟환율 대비 ±30% 괴리 경고 ---
    def _deviation_flag(row: pd.Series) -> tuple[bool, bool]:
        spot = spot_rates.get(row["통화"])
        if spot is None:
            return False, True  # (괴리경고, 스팟환율없음)
        deviation = abs(row["적용환율"] - spot) / spot
        return deviation > SPOT_DEVIATION_THRESHOLD, False

    flags = clean.apply(_deviation_flag, axis=1, result_type="expand")
    clean["스팟환율괴리경고"] = flags[0]
    clean["스팟환율없음"] = flags[1]

    # --- 규칙 6: 연체 플래그 ---
    clean["연체여부"] = clean["만기일"] < pd.Timestamp(report_date)

    # --- 규칙 7: 네고 플래그 ---
    clean["네고플래그"] = (clean["구분"] == "AR") & (clean["네고여부"] == "Y")

    summary = {
        "총라인수": len(ledger),
        "격리_금액결측또는0": int((quarantined["격리사유"] == "금액결측또는0").sum()),
        "격리_날짜형식오류": int((quarantined["격리사유"] == "날짜형식오류").sum()),
        "격리_만기일선행오류": int((quarantined["격리사유"] == "만기일선행오류").sum()),
        "격리_합계": len(quarantined),
        "제외_반제완료": len(excluded_settled),
        "집계대상": len(clean),
        "경고_스팟환율괴리": int(clean["스팟환율괴리경고"].sum()),
        "경고_스팟환율없음": int(clean["스팟환율없음"].sum()),
        "플래그_연체": int(clean["연체여부"].sum()),
        "플래그_네고": int(clean["네고플래그"].sum()),
    }

    return ValidationResult(
        clean=clean,
        quarantined=quarantined,
        excluded_settled=excluded_settled,
        summary=summary,
    )
