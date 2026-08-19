"""AR/AP 원장 로더 — 서로 다른 SAP 원본 스키마를 표준 필드로 정규화한다.

원본 파일(AR: 실습AR_300건.xlsx / AP: 실습AP_300건_v2.xlsx)은 서로 다른 SAP 리포트에서
추출되어 컬럼 구성이 다르고, 둘 다 "적용환율" 컬럼이 없다 (PRD §4.1.1~4.1.3 참조).
적용환율은 validate.py 단계에서 원화금액÷외화금액으로 역산한다 (이 모듈은 원본 값만 옮겨온다).

AP 원장의 주의사항: 전기일에 해당하는 실제 날짜가 "회계연도"라는 이름의 컬럼에 들어있다
(SAP 추출 시 필드명이 잘못 매핑된 것으로 추정 — PRD §11 확인 필요 항목).
"""
from __future__ import annotations

import pandas as pd

# 표준화된 내부 스키마. 이후 validate.py/fx_engine.py는 전부 이 스키마를 기준으로 동작한다.
STANDARD_COLUMNS = [
    "구분",       # "AR" / "AP"
    "전표번호",
    "전기일",
    "만기일",
    "통화",
    "외화금액",
    "원화금액",
    "거래처",
    "계정과목",
    "네고여부",    # AR 전용. AP는 항상 None
    "반제일",      # AP 전용. AR은 항상 NaT (원본에 정산여부 컬럼 없음 → 전량 미결제로 간주, §4.1.1)
    "원본행",      # 원본 엑셀 행 번호(헤더=1행 기준) — 오류 메시지에서 라인 추적용
]


def _parse_date_series(series: pd.Series) -> pd.Series:
    """'YYYY.MM.DD' 포맷 문자열을 datetime으로 변환. 포맷이 안 맞거나 결측이면 NaT."""
    return pd.to_datetime(series, format="%Y.%m.%d", errors="coerce")


def load_ar(path: str) -> pd.DataFrame:
    """실습AR_300건.xlsx 형태의 AR 원장을 표준 스키마로 정규화한다."""
    raw = pd.read_excel(path)

    df = pd.DataFrame(
        {
            "구분": "AR",
            "전표번호": raw["전표 번호"],
            "전기일": _parse_date_series(raw["전기일"]),
            "만기일": _parse_date_series(raw["만기일"]),
            "통화": raw["전표통화"].str.strip().str.upper(),
            "외화금액": pd.to_numeric(raw["미수금액(TC)"], errors="coerce"),
            "원화금액": pd.to_numeric(raw["미수금액(LC)"], errors="coerce"),
            "거래처": raw["비즈니스파트너명"],
            "계정과목": raw["G/L계정명"],
            "네고여부": raw["네고여부"].str.strip().str.upper(),
            "반제일": pd.NaT,
            "원본행": raw.index + 2,  # 1행=헤더, 데이터는 2행부터
        }
    )
    return df[STANDARD_COLUMNS]


def load_ap(path: str) -> pd.DataFrame:
    """실습AP_300건_v2.xlsx 형태의 AP 원장을 표준 스키마로 정규화한다.

    "회계연도" 컬럼에 실제 전기일 날짜값이 들어있는 것을 전기일로 매핑한다 (모듈 docstring 참조).
    """
    raw = pd.read_excel(path)

    df = pd.DataFrame(
        {
            "구분": "AP",
            "전표번호": raw["전표 번호"],
            "전기일": _parse_date_series(raw["회계연도"]),
            "만기일": _parse_date_series(raw["만기일"]),
            "통화": raw["전표 통화 키"].str.strip().str.upper(),
            "외화금액": pd.to_numeric(raw["전표 통화 금액"], errors="coerce"),
            "원화금액": pd.to_numeric(raw["회사 코드 통화 금액"], errors="coerce"),
            "거래처": raw["전표 헤더 텍스트"],  # 거래처 전용 컬럼 없음 — 적요 성격 (PRD §4.1.2)
            "계정과목": raw["G/L 계정: 내역"],
            "네고여부": None,
            "반제일": _parse_date_series(raw["반제일"]),
            "원본행": raw.index + 2,
        }
    )
    return df[STANDARD_COLUMNS]


def load_ledger(ar_path: str, ap_path: str) -> pd.DataFrame:
    """AR/AP 원장을 함께 로드해 하나의 표준 스키마 DataFrame으로 합친다."""
    ar = load_ar(ar_path)
    ap = load_ap(ap_path)
    return pd.concat([ar, ap], ignore_index=True)
