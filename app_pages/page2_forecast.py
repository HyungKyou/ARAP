"""2번 페이지 — 환율예측치 (PRD F3 대응).

시나리오(P10~P90)부터 보여주지 않고, 기관별 당월말/올해 분기별/내년도 전망치를
먼저 보여준 다음 그 아래에 시나리오를 배치한다 (요청 순서 그대로).
"""
from __future__ import annotations

import streamlit as st

from src.formatting import fmt_rate
from src.forecast_source import samples_to_horizon_dataframe


def render(shared) -> None:
    report_date = shared.report_date
    forecast_samples = shared.forecast_samples
    ai_scenarios = shared.ai_scenarios
    forecast_warnings = shared.forecast_warnings

    st.title("🔮 환율예측치")
    st.caption(f"보고기준일: {report_date.isoformat()} · 원/달러 기준")
    st.info(
        "⚠️ v1 스텁: 실제 리서치 자료 실시간 수집 대신 예시 표본을 사용합니다 "
        "(로드맵 항목 — `ForecastSource` 인터페이스만 교체하면 실 수집기로 전환 가능)."
    )

    st.header("기관별 전망치")
    horizon_df = samples_to_horizon_dataframe(forecast_samples, report_date)
    month_col = [c for c in horizon_df.columns if c.endswith("말")][0]
    rate_cols = [c for c in horizon_df.columns if c not in ("기관명", "발표일", "출처")]
    st.dataframe(
        horizon_df.style.format({c: fmt_rate for c in rate_cols}),
        width="stretch",
        hide_index=True,
    )
    st.caption(f"'{month_col}' 컬럼이 아래 시나리오(P10~P90) 산출에 실제로 쓰이는 값입니다.")

    st.divider()

    st.header("예측환율 시나리오 (백분위 기반)")
    for w in forecast_warnings:
        st.warning(w)

    scenario_cols = st.columns(4)
    for col, sc in zip(scenario_cols, ai_scenarios):
        col.metric(sc.label, fmt_rate(sc.rate))
    st.caption(f"출처: {ai_scenarios[0].source if ai_scenarios else '-'}")
