"""AR/AP 원본 스키마 → 표준 스키마 매핑이 실제 샘플 파일에서 정확한지 검증한다.

값은 엑셀을 직접 열어 확인한 원본 그대로이며(회귀 방지용), 컬럼이 밀리거나
전기일/만기일이 뒤바뀌는 등의 매핑 실수를 잡기 위한 테스트다.
"""
from pathlib import Path

import pandas as pd

from src.ingest import load_ap, load_ar, load_ledger

ROOT = Path(__file__).resolve().parent.parent
AR_PATH = ROOT / "실습AR_300건.xlsx"
AP_PATH = ROOT / "실습AP_300건_v2.xlsx"


def test_load_ar_first_row_matches_raw_file():
    df = load_ar(str(AR_PATH))
    row = df.iloc[0]

    assert row["구분"] == "AR"
    assert row["전기일"] == pd.Timestamp("2026-02-17")
    assert row["만기일"] == pd.Timestamp("2026-05-18")
    assert row["통화"] == "EUR"
    assert row["외화금액"] == 157512.98
    assert row["원화금액"] == 224806131
    assert row["거래처"] == "ASML Holding"
    assert row["네고여부"] == "N"
    assert pd.isna(row["반제일"])  # AR 원본에는 정산여부 컬럼이 없음


def test_load_ar_row_count_and_columns():
    df = load_ar(str(AR_PATH))
    assert len(df) == 300
    assert list(df.columns) == [
        "구분", "전표번호", "전기일", "만기일", "통화", "외화금액",
        "원화금액", "거래처", "계정과목", "네고여부", "반제일", "원본행",
    ]


def test_load_ap_first_row_matches_raw_file():
    df = load_ap(str(AP_PATH))
    row = df.iloc[0]

    assert row["구분"] == "AP"
    # "회계연도" 컬럼에 들어있는 실제 날짜값을 전기일로 사용해야 한다 (PRD §4.1.2)
    assert row["전기일"] == pd.Timestamp("2025-11-07")
    assert row["만기일"] == pd.Timestamp("2025-12-07")
    assert row["통화"] == "JPY"
    assert row["외화금액"] == 527539
    assert row["원화금액"] == 4686498
    assert row["계정과목"] == "외상매입금(외화)"
    assert row["네고여부"] is None
    assert pd.isna(row["반제일"])  # 샘플은 전량 미결제


def test_load_ap_row_count():
    df = load_ap(str(AP_PATH))
    assert len(df) == 300


def test_load_ledger_concatenates_both():
    ledger = load_ledger(str(AR_PATH), str(AP_PATH))
    assert len(ledger) == 600
    assert set(ledger["구분"].unique()) == {"AR", "AP"}


def test_currency_universe_is_not_hardcoded_assumption():
    """PRD 초안은 USD/EUR/JPY만 가정했으나 실제 파일엔 CNY도 있다 — 회귀 방지."""
    ledger = load_ledger(str(AR_PATH), str(AP_PATH))
    assert set(ledger["통화"].unique()) == {"USD", "EUR", "JPY", "CNY"}
