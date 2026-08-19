"""4번 페이지 — 가정사항 및 주의사항 + 리포트 다운로드."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.forecast_source import samples_to_dataframe
from src.manual_input import manual_entries_to_scenarios
from src.pnl_engine import ScenarioInput, build_pnl_matrix
from src.report_export import ASSUMPTIONS_TEXT, build_excel_report

KNOWN_LIMITATIONS = """\
[현재 버전(v1)에서 아직 지원하지 않는 것 — 사용 전 반드시 확인]

- 2번 페이지의 기관별 전망치는 실제 리서치 자료 실시간 수집이 아니라 예시(mock) 데이터입니다.
  실제 서비스 전환 시 수집 로직만 교체될 예정이며, 계산 방식 자체는 바뀌지 않습니다.
- PDF 다운로드는 아직 지원하지 않습니다 (Excel 다운로드만 가능).
- 사내 접근 권한 통제(로그인 등)가 없습니다. 거래처명 등 민감정보가 그대로 노출되므로
  외부 공유나 사내 공개 배포 전에는 반드시 별도 접근 통제를 적용해야 합니다.
- 평일 오전 자동 실행 등 예약 실행 기능은 없습니다. 매번 직접 실행해야 합니다.
"""


def render(shared) -> None:
    st.title("📐 가정사항 및 주의사항")

    st.header("계산 가정사항")
    st.text(ASSUMPTIONS_TEXT)

    st.header("현재 버전의 한계")
    st.warning(KNOWN_LIMITATIONS)

    st.divider()
    st.header("📤 리포트 다운로드")

    clean_with_usd = shared.clean_with_usd
    result = shared.result
    report_date = shared.report_date
    ai_scenarios = shared.ai_scenarios
    forecast_samples = shared.forecast_samples

    manual_scenarios = manual_entries_to_scenarios(st.session_state.manual_entries)
    all_scenarios: list[ScenarioInput] = ai_scenarios + manual_scenarios
    scenario_order = [s.label for s in all_scenarios]
    matrix = build_pnl_matrix(clean_with_usd, all_scenarios, report_date)

    if st.session_state.manual_entries:
        manual_history_df = pd.DataFrame(
            [{"환율": e.rate, "입력시각": e.entered_at} for e in st.session_state.manual_entries]
        )
    else:
        manual_history_df = pd.DataFrame()

    col_excel, col_pdf = st.columns(2)
    with col_excel:
        excel_bytes = build_excel_report(
            pnl_matrix=matrix,
            clean_df=clean_with_usd,
            quarantined_df=result.quarantined,
            excluded_settled_df=result.excluded_settled,
            forecast_df=samples_to_dataframe(forecast_samples),
            manual_history_df=manual_history_df,
            scenario_order=scenario_order,
        )
        st.download_button(
            "⬇️ Excel 다운로드",
            data=excel_bytes,
            file_name=f"ARAP_환차환산손익_{report_date.isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
    with col_pdf:
        st.button("⬇️ PDF 다운로드 (미지원)", disabled=True, width="stretch")
        st.caption("PDF 출력 우선순위는 PRD §11 확인 필요 항목 — 정책 확정 후 구현 예정")
