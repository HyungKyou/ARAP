"""F5. 리포트 Excel 다운로드 (PRD §5 F5).

PDF 출력은 §11 확인 필요 항목(출력 포맷 우선순위)이 아직 정책 확정 전이라 v1 범위에서
버튼만 두고 구현하지 않는다 (app.py의 TODO 참고).
"""
from __future__ import annotations

import io

import pandas as pd

ASSUMPTIONS_TEXT = """\
[계산 가정사항 / 고지문]

1. 다통화(EUR/JPY/CNY 등) 익스포저는 당일 스팟환율로 USD 환산 후 원/달러 단일 익스포저로
   통합해 처리합니다 (PRD §6.4, 원/달러 프록시 통합). 이는 근사치이며 EUR/USD, JPY/USD,
   CNY/USD 등 개별 통화 자체의 변동성(교차통화 리스크)은 반영하지 않습니다.
2. 환차손익(실현)/환산손익(미실현) 분류 기준일은 "당월 말"입니다 (만기일 ≤ 당월 말 → 환차손익).
3. 예측환율 4개 시나리오는 AI가 수집한 표본의 백분위수(P10/P50/P75/P90) 기반이며,
   표본이 5건 미만인 경우 최소/중앙/최대 기반 대체 산식을 사용합니다.
4. 수동 입력 환율 시나리오는 AI 시나리오와 별개로 담당자가 직접 입력한 값입니다.
5. AR "네고여부=Y" 라인은 집계에 포함하되 플래그로 표시했습니다(이미 은행에 할인 매각되어
   실질 익스포저가 없을 가능성 — PRD §11 확인 필요).
6. AP G/L계정 중 "외화단기차입금"도 매입채무와 함께 AP 익스포저에 포함했습니다
   (PRD §11 확인 필요 항목, v1 기본값).
"""


ROW_ORDER = ["AR", "AP", "Net"]
KIND_ORDER = ["환차손익", "환산손익", "합계"]


def _reindex_rows_and_columns(pivoted: pd.DataFrame, scenario_order: list[str] | None) -> pd.DataFrame:
    gubun_order = pd.CategoricalIndex(pivoted.index.get_level_values(0), categories=ROW_ORDER, ordered=True)
    kind_order = pd.CategoricalIndex(pivoted.index.get_level_values(1), categories=KIND_ORDER, ordered=True)
    pivoted = pivoted.set_axis(pd.MultiIndex.from_arrays([gubun_order, kind_order]), axis=0).sort_index(level=[0, 1])
    if scenario_order:
        present = [s for s in scenario_order if s in pivoted.columns]
        pivoted = pivoted[present]
    return pivoted


def pivot_pnl_matrix(matrix: pd.DataFrame, scenario_order: list[str] | None = None) -> pd.DataFrame:
    """long-form 매트릭스를 (구분, 손익유형) × 시나리오 형태의 보기 좋은 표로 변환.

    `scenario_order`를 주면 컬럼을 그 순서(예: P10→P50→P75→P90→수동입력)로 고정한다.
    안 주면 pandas 기본(알파벳) 순서로 남는다 — F4 화면에서는 항상 명시적으로 넘길 것.
    """
    pivoted = matrix.pivot_table(index=["구분", "손익유형"], columns="시나리오", values="금액", aggfunc="first")
    return _reindex_rows_and_columns(pivoted, scenario_order)


def pivot_delta_matrix(matrix: pd.DataFrame, scenario_order: list[str] | None = None) -> pd.DataFrame:
    """Base(중앙값) 대비 Delta를 pivot_pnl_matrix와 동일한 행/열 순서로 반환."""
    pivoted = matrix.pivot_table(
        index=["구분", "손익유형"], columns="시나리오", values="Base대비Delta", aggfunc="first"
    )
    return _reindex_rows_and_columns(pivoted, scenario_order)


def _pivot_one_kind(matrix: pd.DataFrame, kind: str, value_col: str, scenario_order: list[str] | None) -> pd.DataFrame:
    subset = matrix[matrix["손익유형"] == kind]
    pivoted = subset.pivot_table(index="구분", columns="시나리오", values=value_col, aggfunc="first")
    row_order = pd.CategoricalIndex(pivoted.index, categories=ROW_ORDER, ordered=True)
    pivoted = pivoted.set_axis(row_order, axis=0).sort_index()
    if scenario_order:
        present = [s for s in scenario_order if s in pivoted.columns]
        pivoted = pivoted[present]
    return pivoted


def pivot_amount_by_kind(matrix: pd.DataFrame, kind: str, scenario_order: list[str] | None = None) -> pd.DataFrame:
    """환차손익/환산손익/합계 중 하나만 골라 구분(AR/AP/Net) × 시나리오 표로 반환 (3번 페이지 — 따로 보기)."""
    return _pivot_one_kind(matrix, kind, "금액", scenario_order)


def pivot_delta_by_kind(matrix: pd.DataFrame, kind: str, scenario_order: list[str] | None = None) -> pd.DataFrame:
    """pivot_amount_by_kind와 동일하지만 Base 대비 Delta 값을 담는다."""
    return _pivot_one_kind(matrix, kind, "Base대비Delta", scenario_order)


def build_excel_report(
    *,
    pnl_matrix: pd.DataFrame,
    clean_df: pd.DataFrame,
    quarantined_df: pd.DataFrame,
    excluded_settled_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    manual_history_df: pd.DataFrame,
    scenario_order: list[str] | None = None,
) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pivot_pnl_matrix(pnl_matrix, scenario_order).to_excel(writer, sheet_name="손익매트릭스")
        matrix_export = pnl_matrix.copy()
        matrix_export.to_excel(writer, sheet_name="손익매트릭스(원본)", index=False)

        clean_df.to_excel(writer, sheet_name="원장상세(집계대상)", index=False)
        if len(quarantined_df):
            quarantined_df.to_excel(writer, sheet_name="격리라인", index=False)
        if len(excluded_settled_df):
            excluded_settled_df.to_excel(writer, sheet_name="제외라인(반제완료)", index=False)

        forecast_df.to_excel(writer, sheet_name="예측환율출처(AI)", index=False)
        if len(manual_history_df):
            manual_history_df.to_excel(writer, sheet_name="수동입력이력", index=False)

        assumptions_df = pd.DataFrame({"계산 가정사항 / 고지문": ASSUMPTIONS_TEXT.splitlines()})
        assumptions_df.to_excel(writer, sheet_name="가정사항", index=False)

    return buffer.getvalue()
