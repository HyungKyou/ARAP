"""3번 페이지 — 환차·환산 (PRD F3-2, F4 대응).

- 수동 환율 입력(입력자 없음) → 입력 즉시 당월 말 기준 환차손익/환산손익 미리보기
- "시나리오 비교에 추가" 시 AI 4개 시나리오와 함께 매트릭스에 반영(최대 5개)
- 환차손익/환산손익/합계를 탭으로 완전히 분리해서 보여준다
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from app_pages.common import display_label
from src.formatting import fmt_krw, fmt_rate, fmt_signed_krw, sign_color
from src.manual_input import (
    MAX_MANUAL_ENTRIES,
    ManualRateEntry,
    append_history,
    load_history,
    manual_entries_to_scenarios,
)
from src.pnl_engine import ScenarioInput, build_pnl_matrix, month_end
from src.report_export import pivot_amount_by_kind, pivot_delta_by_kind

KIND_TABS = {
    "환차손익": ("💱 환차손익 (실현)", "만기일이 당월 말 이전이라 결제가 이미 이루어졌거나 이루어질 것으로 보는 실현 손익"),
    "환산손익": ("📐 환산손익 (미실현)", "만기일이 당월 말 이후라 아직 미결제 상태인 채권·채무를 재평가한 미실현 손익"),
    "합계": ("Σ 합계", "환차손익 + 환산손익"),
}


def _style_amount(df: pd.DataFrame):
    return df.style.format(fmt_krw).map(lambda v: sign_color(v) if isinstance(v, (int, float)) else "")


def render(shared) -> None:
    clean_with_usd = shared.clean_with_usd
    report_date = shared.report_date
    ai_scenarios = shared.ai_scenarios

    st.title("⚖️ 환차·환산")
    st.caption(f"보고기준일: {report_date.isoformat()} · 당월 말 기준: {month_end(report_date):%Y-%m-%d}")

    # ── 수동 환율 입력 + 즉시 미리보기 ────────────────────────────────
    st.header("✍️ 수동 환율 입력")
    st.caption("입력하면 바로 아래에 당월 말 기준 환차손익·환산손익이 자동으로 계산되어 표시됩니다.")

    manual_rate_value = st.number_input(
        "원/달러 예상환율", min_value=0.0, step=1.0, value=1380.0, key="page3_manual_rate"
    )

    preview_scenario = ScenarioInput(label="입력값", rate=manual_rate_value, source="수동 입력(미리보기)")
    preview_matrix = build_pnl_matrix(clean_with_usd, [preview_scenario], report_date)
    preview_pivot = preview_matrix.pivot_table(index="구분", columns="손익유형", values="금액", aggfunc="first")
    preview_pivot = preview_pivot.reindex(index=["AR", "AP", "Net"], columns=["환차손익", "환산손익", "합계"])
    st.dataframe(_style_amount(preview_pivot), width="stretch")

    add_disabled = len(st.session_state.manual_entries) >= MAX_MANUAL_ENTRIES
    if st.button("➕ 이 값을 시나리오 비교에 추가", disabled=add_disabled):
        entry = ManualRateEntry(rate=manual_rate_value, entered_at=datetime.now())
        st.session_state.manual_entries.append(entry)
        append_history(entry)

    if add_disabled:
        st.caption(f"최대 {MAX_MANUAL_ENTRIES}개까지 추가할 수 있습니다.")

    if st.session_state.manual_entries:
        st.write("현재 시나리오 비교에 포함된 수동 입력값")
        for i, e in enumerate(st.session_state.manual_entries):
            st.markdown(f"- **{i + 1}.** {fmt_rate(e.rate)} ({e.entered_at:%Y-%m-%d %H:%M})")
        if st.button("🗑️ 전체 지우기 (이번 세션만)"):
            st.session_state.manual_entries = []

    st.divider()

    # ── 시나리오별 환차·환산손익 (탭으로 완전히 분리) ────────────────────
    st.header("시나리오별 환차·환산손익")
    manual_scenarios = manual_entries_to_scenarios(st.session_state.manual_entries)
    all_scenarios: list[ScenarioInput] = ai_scenarios + manual_scenarios
    scenario_order = [s.label for s in all_scenarios]
    rename_map = {s.label: display_label(s) for s in all_scenarios}
    st.caption("🤖 = AI 자동수집 시나리오 (2번 페이지)  ·  🖊️ = 위에서 추가한 수동 입력")

    matrix = build_pnl_matrix(clean_with_usd, all_scenarios, report_date)
    base_scenarios = [s for s in all_scenarios if s.is_base]
    base_label = display_label(base_scenarios[0]) if base_scenarios else None

    tabs = st.tabs([label for label, _ in KIND_TABS.values()])
    for tab, (kind, (_, help_text)) in zip(tabs, KIND_TABS.items()):
        with tab:
            st.caption(help_text)

            amount = pivot_amount_by_kind(matrix, kind, scenario_order).rename(columns=rename_map)
            st.subheader("금액 (KRW)")
            st.dataframe(_style_amount(amount), width="stretch")

            delta = pivot_delta_by_kind(matrix, kind, scenario_order).rename(columns=rename_map)
            non_base_cols = [c for c in delta.columns if c != base_label]
            formatters = {c: fmt_signed_krw for c in non_base_cols}
            if base_label:
                formatters[base_label] = lambda _v: "(기준)"
            styled_delta = delta.style.format(formatters)
            if non_base_cols:
                styled_delta = styled_delta.map(
                    lambda v: sign_color(v) if isinstance(v, (int, float)) else "", subset=non_base_cols
                )
            st.subheader("Base(🤖 중앙값) 대비 Delta")
            st.dataframe(styled_delta, width="stretch")

    with st.expander("📜 전체 수동 입력 이력 (감사 추적용 — 오늘 반영 여부와 무관한 전체 기록)"):
        full_history = load_history()
        if full_history:
            history_df = pd.DataFrame([{"환율": e.rate, "입력시각": e.entered_at} for e in full_history])
            st.dataframe(history_df.style.format({"환율": fmt_rate}), width="stretch")
        else:
            st.caption("아직 저장된 수동 입력 이력이 없습니다.")
