"""1번 페이지 — 당일 AR/AP 분석 (PRD F1, F2 대응).

만기일자별 AR/AP 금액 그래프(AR/AP/Net 선택 가능) + 상세 표 + 가중평균 기표환율.
"""
from __future__ import annotations

import streamlit as st

from src.charts import build_f1_chart
from src.formatting import fmt_krw, fmt_rate
from src.fx_engine import booking_rate_by_month, booking_rate_overview
from src.maturity_view import build_maturity_buckets


def render(shared) -> None:
    result = shared.result
    clean_with_usd = shared.clean_with_usd
    report_date = shared.report_date

    st.title("📊 당일 AR/AP 분석")
    st.caption(f"보고기준일: {report_date.isoformat()}")

    kpi_cols = st.columns(2)
    kpi_cols[0].metric("총 라인 수", f"{result.summary['총라인수']:,}")
    kpi_cols[1].metric("집계 대상", f"{result.summary['집계대상']:,}")

    st.caption("데이터 품질 플래그 — 배지에 마우스를 올리면 의미를 설명합니다.")
    badge_cols = st.columns(5)
    n_quarantine = result.summary["격리_합계"]
    n_settled = result.summary["제외_반제완료"]
    n_overdue = result.summary["플래그_연체"]
    n_nego = result.summary["플래그_네고"]
    n_spot_warn = result.summary["경고_스팟환율괴리"] + result.summary["경고_스팟환율없음"]

    with badge_cols[0]:
        st.badge(
            f"격리 {n_quarantine}건", icon="🚫", color=("gray" if n_quarantine == 0 else "red"),
            help="금액 결측/0, 날짜 오류, 만기<전기 오류로 계산에서 제외된 라인입니다 (PRD §4.1.3 규칙 1~3).",
        )
    with badge_cols[1]:
        st.badge(
            f"제외 {n_settled}건", icon="✅", color=("gray" if n_settled == 0 else "blue"),
            help="AP 반제일이 있어 이미 정산된(반제완료) 라인입니다. 오류가 아니라 정상적으로 집계에서 빠진 것입니다.",
        )
    with badge_cols[2]:
        st.badge(
            f"연체 {n_overdue}건", icon="⏰", color=("gray" if n_overdue == 0 else "orange"),
            help="만기일이 보고기준일보다 이전인데 원장에 남아있는 라인입니다. 환차손익 그룹으로 집계됩니다.",
        )
    with badge_cols[3]:
        st.badge(
            f"네고 {n_nego}건", icon="🏦", color=("gray" if n_nego == 0 else "violet"),
            help="이미 은행에 할인 매각된 수출채권(AR)입니다. v1 기본값으로 집계에는 포함하고 표시만 합니다 (PRD §11 확인 필요).",
        )
    with badge_cols[4]:
        st.badge(
            f"스팟이상 {n_spot_warn}건", icon="⚠️", color=("gray" if n_spot_warn == 0 else "red"),
            help="적용환율이 당일 매매기준율과 ±30% 이상 차이나거나, 해당 통화의 매매기준율이 입력되지 않은 라인입니다.",
        )

    st.divider()

    st.header("만기일자별 AR/AP (USD 환산)")
    visible = st.segmented_control(
        "표시할 항목",
        ["AR", "AP", "Net"],
        default=["AR", "AP", "Net"],
        selection_mode="multi",
        key="page1_visible_series",
    )
    if not visible:
        visible = ["AR", "AP", "Net"]

    buckets = build_maturity_buckets(clean_with_usd, report_date)
    st.altair_chart(build_f1_chart(buckets, tuple(visible)), width="stretch")

    with st.expander("상세 표로 보기"):
        st.dataframe(buckets.style.format({"AR": fmt_krw, "AP": fmt_krw, "Net": fmt_krw}), width="stretch")

    st.divider()

    st.header("AR/AP 가중평균 기표환율")
    overview = booking_rate_overview(clean_with_usd)
    c1, c2 = st.columns(2)
    c1.metric("AR 기표환율 (원/달러)", fmt_rate(overview["AR"]))
    c2.metric("AP 기표환율 (원/달러)", fmt_rate(overview["AP"]))
    with st.expander("만기월별 기표환율 브레이크다운"):
        st.dataframe(booking_rate_by_month(clean_with_usd).style.format({"기표환율": fmt_rate}), width="stretch")

    st.divider()

    with st.expander("🔎 원장 라인 상세 / 격리·제외 라인 (참고)"):
        tab1, tab2 = st.tabs(["원장 상세(집계대상)", "격리/제외 라인"])
        with tab1:
            st.caption("연체여부·네고플래그·스팟환율괴리경고 컬럼으로 위 배지의 근거 라인을 직접 확인할 수 있습니다.")
            st.dataframe(clean_with_usd, width="stretch")
        with tab2:
            st.write("격리된 라인 (오류 — 계산에서 제외됨)")
            st.dataframe(result.quarantined, width="stretch")
            st.write("제외된 라인 (AP 반제완료 — 정상 케이스)")
            st.dataframe(result.excluded_settled, width="stretch")
