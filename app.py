"""AR/AP 환율 예측 기반 환차·환산손익 리포트 Agent — Streamlit 진입점(라우터).

사이드바(전역 입력)와 공통 계산 파이프라인은 여기서 한 번만 실행하고, 화면은
4개 페이지(app_pages/)로 나눠 보여준다. 페이지 함수들은 이 파일에서 계산한 결과를
`shared` 객체로 받아서 그리기만 한다 — 계산 로직을 페이지 파일에 새로 두지 않는다.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app_pages import page1_ar_ap, page2_forecast, page3_pnl, page4_notes
from src.fx_engine import DEFAULT_SPOT_RATES, add_usd_amount
from src.forecast_source import MockForecastSource, compute_percentile_scenarios
from src.ingest import load_ap, load_ar
from src.validate import validate_and_enrich

AR_SAMPLE_PATH = ROOT / "실습AR_300건.xlsx"
AP_SAMPLE_PATH = ROOT / "실습AP_300건_v2.xlsx"
LOGO_PATH = ROOT / "현대제철로고.jpg"

st.set_page_config(page_title="AR/AP 환차·환산손익 리포트", layout="wide", page_icon="💱")

if LOGO_PATH.exists():
    st.logo(str(LOGO_PATH), size="large")

if "manual_entries" not in st.session_state:
    # 세션은 항상 빈 목록으로 시작한다 — 과거 이력을 그대로 불러오면 안 되는 이유는
    # STAGE4_검토보고서.md와 src/manual_input.py 참고 (4단계에서 발견·수정한 버그).
    st.session_state.manual_entries = []

# ══════════════════════════════════════════════════════════════════════
# 사이드바 — 전역 입력 (모든 페이지에서 공유)
# ══════════════════════════════════════════════════════════════════════
st.sidebar.header("📥 입력")

ar_file = st.sidebar.file_uploader("AR 원장 (xlsx)", type="xlsx")
ap_file = st.sidebar.file_uploader("AP 원장 (xlsx)", type="xlsx")
if ar_file is None or ap_file is None:
    st.sidebar.caption("파일을 올리지 않으면 번들된 샘플 파일을 사용합니다.")
st.sidebar.caption(
    "⚠️ 다른 파일도 업로드할 수 있지만, 번들 샘플과 **컬럼 구성이 동일한 SAP 추출 파일**이어야 합니다 "
    "(컬럼명이 다르면 오류가 표시됩니다)."
)

report_date: date = st.sidebar.date_input("보고기준일", value=date.today())

AR_REQUIRED_COLUMNS = [
    "전표 번호", "전기일", "만기일", "전표통화", "미수금액(TC)", "미수금액(LC)", "비즈니스파트너명",
    "G/L계정명", "네고여부",
]
AP_REQUIRED_COLUMNS = [
    "전표 번호", "회계연도", "만기일", "전표 통화 키", "전표 통화 금액", "회사 코드 통화 금액",
    "전표 헤더 텍스트", "G/L 계정: 내역", "반제일",
]


def _load_or_stop(loader, source, label: str, required_columns: list[str]) -> pd.DataFrame:
    try:
        return loader(source)
    except KeyError as e:
        st.error(
            f"**{label} 원장 파일을 읽을 수 없습니다.** 필요한 컬럼 {e}이(가) 없습니다.\n\n"
            f"업로드한 파일이 번들 샘플과 다른 컬럼 구성을 쓰고 있는 것 같습니다. "
            f"{label} 원장은 아래 컬럼명을 (순서와 무관하게) 그대로 포함해야 합니다:\n\n"
            + "\n".join(f"- `{c}`" for c in required_columns)
        )
        st.stop()
    except Exception as e:  # 손상된 파일, 잘못된 시트 등 그 외 오류
        st.error(f"**{label} 원장 파일을 읽는 중 오류가 발생했습니다:** {e}")
        st.stop()


ar_source = ar_file if ar_file is not None else str(AR_SAMPLE_PATH)
ap_source = ap_file if ap_file is not None else str(AP_SAMPLE_PATH)
ar_df = _load_or_stop(load_ar, ar_source, "AR", AR_REQUIRED_COLUMNS)
ap_df = _load_or_stop(load_ap, ap_source, "AP", AP_REQUIRED_COLUMNS)
ledger = pd.concat([ar_df, ap_df], ignore_index=True)

st.sidebar.divider()
st.sidebar.header("💹 당일 매매기준율")
st.sidebar.caption("원장에 있는 통화만 KRW 기준으로 입력받고, 참고용 교차환율은 자동 계산됩니다.")
currencies_in_ledger = sorted(c for c in ledger["통화"].dropna().unique())
spot_rates: dict[str, float] = {}
for currency in currencies_in_ledger:
    default_value = DEFAULT_SPOT_RATES.get(currency, 0.0)
    spot_rates[currency] = st.sidebar.number_input(
        f"{currency}/KRW", min_value=0.0, value=float(default_value), step=1.0, key=f"spot_{currency}"
    )


def _cross_rate(numerator_ccy: str, denominator_ccy: str) -> float | None:
    num, den = spot_rates.get(numerator_ccy), spot_rates.get(denominator_ccy)
    if not num or not den:
        return None
    return num / den


usd_jpy = _cross_rate("USD", "JPY")  # 엔/달러
eur_usd = _cross_rate("EUR", "USD")  # 달러/유로

st.sidebar.caption("참고용 교차환율 (자동 계산, 입력값 아님)")
cross_cols = st.sidebar.columns(2)
cross_cols[0].metric("USD/JPY", f"{usd_jpy:,.2f}" if usd_jpy else "—")
cross_cols[1].metric("EUR/USD", f"{eur_usd:,.4f}" if eur_usd else "—")

# ══════════════════════════════════════════════════════════════════════
# 공통 계산 파이프라인 (한 번만 실행 → 각 페이지가 결과만 소비)
# ══════════════════════════════════════════════════════════════════════
result = validate_and_enrich(ledger, spot_rates, report_date)
clean_with_usd = add_usd_amount(result.clean, spot_rates)

forecast_samples = MockForecastSource().fetch_samples(target_month=report_date.strftime("%Y-%m"))
ai_scenarios, forecast_warnings = compute_percentile_scenarios(forecast_samples)

shared = SimpleNamespace(
    report_date=report_date,
    spot_rates=spot_rates,
    result=result,
    clean_with_usd=clean_with_usd,
    forecast_samples=forecast_samples,
    ai_scenarios=ai_scenarios,
    forecast_warnings=forecast_warnings,
)

# ══════════════════════════════════════════════════════════════════════
# 페이지 라우팅
# ══════════════════════════════════════════════════════════════════════
pages = [
    st.Page(lambda: page1_ar_ap.render(shared), title="당일 AR/AP 분석", icon="📊", url_path="ar-ap", default=True),
    st.Page(lambda: page2_forecast.render(shared), title="환율예측치", icon="🔮", url_path="forecast"),
    st.Page(lambda: page3_pnl.render(shared), title="환차·환산", icon="⚖️", url_path="pnl"),
    st.Page(lambda: page4_notes.render(shared), title="가정사항 및 주의사항", icon="📐", url_path="notes"),
]
st.navigation(pages).run()
