"""PRD §4.1.3 검증/정제 규칙 7개를 합성 데이터로 각각 검증한다.

샘플 엑셀 파일만으로는 일부 경로(AP 반제 완료, 스팟환율 괴리, 알 수 없는 통화 등)가
전혀 발생하지 않으므로(예: AP 반제일은 300건 전량 비어있음), 여기서는 규칙별로
합성 라인을 직접 구성해 각 분기를 강제로 통과시킨다.
"""
from datetime import date

import pandas as pd
import pytest

from src.ingest import STANDARD_COLUMNS
from src.validate import validate_and_enrich

REPORT_DATE = date(2026, 8, 19)
SPOT_RATES = {"USD": 1380.0, "EUR": 1500.0}


def _row(**overrides) -> dict:
    base = {
        "구분": "AR",
        "전표번호": 0,
        "전기일": pd.Timestamp("2026-01-01"),
        "만기일": pd.Timestamp("2026-09-01"),
        "통화": "USD",
        "외화금액": 1000.0,
        "원화금액": 1380000.0,
        "거래처": "테스트거래처",
        "계정과목": "외상매출금(외화)",
        "네고여부": "N",
        "반제일": pd.NaT,
        "원본행": 2,
    }
    base.update(overrides)
    return base


@pytest.fixture
def ledger() -> pd.DataFrame:
    rows = [
        _row(전표번호=1),  # 정상 AR/USD, 미래 만기, 스팟환율과 정확히 일치
        _row(  # 정상 AR/EUR, 이미 만기 지난 + 네고 처리
            전표번호=2, 통화="EUR", 외화금액=1000.0, 원화금액=1500000.0,
            만기일=pd.Timestamp("2026-07-01"), 네고여부="Y",
        ),
        _row(전표번호=3, 외화금액=0.0),  # 규칙1: 외화금액 0
        _row(전표번호=4, 원화금액=float("nan")),  # 규칙1: 원화금액 결측
        _row(전표번호=5, 전기일=pd.NaT),  # 규칙2: 날짜 파싱 실패(전기일)
        _row(전표번호=6, 만기일=pd.NaT),  # 규칙2: 날짜 파싱 실패(만기일)
        _row(  # 규칙3: 만기일 < 전기일
            전표번호=7, 전기일=pd.Timestamp("2026-05-01"), 만기일=pd.Timestamp("2026-01-01"),
        ),
        _row(  # 규칙5: AP 반제완료 → 제외
            전표번호=8, 구분="AP", 네고여부=None, 반제일=pd.Timestamp("2026-08-01"),
        ),
        _row(전표번호=9, 구분="AP", 네고여부=None),  # 정상 AP, 오픈아이템
        _row(  # 규칙4: 스팟환율 대비 33% 괴리 (EUR: 1500 spot, 라인 rate = 2000)
            전표번호=10, 통화="EUR", 외화금액=1000.0, 원화금액=2000000.0,
        ),
        _row(  # 스팟환율표에 없는 통화(GBP) → 괴리 계산 불가, "스팟환율없음"으로 플래그
            전표번호=11, 통화="GBP", 외화금액=1000.0, 원화금액=1700000.0,
        ),
    ]
    return pd.DataFrame(rows)[STANDARD_COLUMNS]


def test_quarantine_amount_missing_or_zero(ledger):
    result = validate_and_enrich(ledger, SPOT_RATES, REPORT_DATE)
    reasons = dict(zip(result.quarantined["전표번호"], result.quarantined["격리사유"]))
    assert reasons[3] == "금액결측또는0"
    assert reasons[4] == "금액결측또는0"


def test_quarantine_bad_date(ledger):
    result = validate_and_enrich(ledger, SPOT_RATES, REPORT_DATE)
    reasons = dict(zip(result.quarantined["전표번호"], result.quarantined["격리사유"]))
    assert reasons[5] == "날짜형식오류"
    assert reasons[6] == "날짜형식오류"


def test_quarantine_maturity_before_posting(ledger):
    result = validate_and_enrich(ledger, SPOT_RATES, REPORT_DATE)
    reasons = dict(zip(result.quarantined["전표번호"], result.quarantined["격리사유"]))
    assert reasons[7] == "만기일선행오류"


def test_ap_settled_line_excluded_not_quarantined(ledger):
    result = validate_and_enrich(ledger, SPOT_RATES, REPORT_DATE)
    assert 8 in set(result.excluded_settled["전표번호"])
    assert 8 not in set(result.quarantined["전표번호"])
    assert 8 not in set(result.clean["전표번호"])


def test_clean_set_excludes_quarantined_and_settled(ledger):
    result = validate_and_enrich(ledger, SPOT_RATES, REPORT_DATE)
    clean_ids = set(result.clean["전표번호"])
    assert clean_ids == {1, 2, 9, 10, 11}


def test_overdue_flag(ledger):
    result = validate_and_enrich(ledger, SPOT_RATES, REPORT_DATE)
    flags = dict(zip(result.clean["전표번호"], result.clean["연체여부"]))
    assert not flags[1]  # 미래 만기
    assert flags[2]  # 2026-07-01 < 2026-08-19


def test_nego_flag_defaults_to_included_but_flagged(ledger):
    result = validate_and_enrich(ledger, SPOT_RATES, REPORT_DATE)
    flags = dict(zip(result.clean["전표번호"], result.clean["네고플래그"]))
    assert flags[2]  # 네고=Y 라인도 집계에 포함되되 플래그만 표시
    assert not flags[1]


def test_spot_deviation_warning(ledger):
    result = validate_and_enrich(ledger, SPOT_RATES, REPORT_DATE)
    flags = dict(zip(result.clean["전표번호"], result.clean["스팟환율괴리경고"]))
    assert flags[10]  # 라인환율 2000 vs 스팟 1500 → 33% 괴리
    assert not flags[1]  # 라인환율 1380 vs 스팟 1380 → 괴리 없음


def test_unknown_currency_flagged_not_crashed(ledger):
    result = validate_and_enrich(ledger, SPOT_RATES, REPORT_DATE)
    row = result.clean[result.clean["전표번호"] == 11].iloc[0]
    assert row["스팟환율없음"]
    assert not row["스팟환율괴리경고"]  # 비교 불가하므로 경고 아님(별도 플래그로 구분)


def test_summary_counts_are_consistent(ledger):
    result = validate_and_enrich(ledger, SPOT_RATES, REPORT_DATE)
    s = result.summary
    assert s["총라인수"] == len(ledger)
    assert s["격리_합계"] == len(result.quarantined) == 5
    assert s["제외_반제완료"] == len(result.excluded_settled) == 1
    assert s["집계대상"] == len(result.clean) == 5
