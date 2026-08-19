"""1단계 검증 스크립트.

샘플 AR/AP 원장을 실제로 읽어 정규화→검증→USD환산→기표환율 계산까지 돌려보고,
격리/제외/플래그된 라인 수와 AR/AP 가중평균 기표환율을 콘솔에 출력한다.

실행: python scripts/verify.py  (프로젝트 루트에서)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 기본 코드페이지에서 한글 깨짐 방지

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ingest import load_ledger
from src.validate import validate_and_enrich
from src.fx_engine import (
    StaticSpotRateSource,
    add_usd_amount,
    booking_rate_by_month,
    booking_rate_overview,
)

AR_PATH = ROOT / "실습AR_300건.xlsx"
AP_PATH = ROOT / "실습AP_300건_v2.xlsx"


def main() -> None:
    report_date = date.today()
    spot_rates = StaticSpotRateSource().get_rates()

    ledger = load_ledger(str(AR_PATH), str(AP_PATH))
    result = validate_and_enrich(ledger, spot_rates, report_date)

    print("=" * 60)
    print(f"보고기준일: {report_date.isoformat()}")
    print(f"스팟환율(스텁): {spot_rates}")
    print("=" * 60)

    print("\n[요약 카운트]")
    for key, value in result.summary.items():
        print(f"  {key}: {value}")

    if len(result.quarantined):
        print("\n[격리된 라인 상세]")
        cols = ["구분", "전표번호", "원본행", "격리사유", "전기일", "만기일", "외화금액", "원화금액"]
        print(result.quarantined[cols].to_string(index=False))
    else:
        print("\n[격리된 라인 없음]")

    print("\n[통화별 라인 수 (집계 대상 기준)]")
    print(result.clean.groupby(["구분", "통화"]).size().to_string())

    clean_with_usd = add_usd_amount(result.clean, spot_rates)

    print("\n[AR/AP 전체 가중평균 기표환율 (§6.2)]")
    overview = booking_rate_overview(clean_with_usd)
    for gubun, rate in overview.items():
        print(f"  {gubun}: {rate:,.2f}")

    print("\n[만기월별 가중평균 기표환율 브레이크다운]")
    by_month = booking_rate_by_month(clean_with_usd)
    print(by_month.to_string(index=False))

    if result.summary["경고_스팟환율괴리"]:
        print("\n[스팟환율 괴리 경고 라인]")
        warn = clean_with_usd[clean_with_usd["스팟환율괴리경고"]]
        print(warn[["구분", "전표번호", "통화", "적용환율"]].to_string(index=False))


if __name__ == "__main__":
    main()
