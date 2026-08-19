"""F5 Excel 내보내기 스모크 테스트 — 크래시 없이 유효한 xlsx 바이트를 만드는지만 확인."""
from datetime import date

import pandas as pd

from src.forecast_source import MockForecastSource, samples_to_dataframe
from src.pnl_engine import ScenarioInput, build_pnl_matrix
from src.report_export import build_excel_report, pivot_pnl_matrix

REPORT_DATE = date(2026, 8, 19)


def test_pivot_and_build_excel_report_smoke():
    df = pd.DataFrame(
        [
            {"구분": "AR", "만기일": pd.Timestamp("2026-07-01"), "원화금액": 1_300_000.0, "USD환산금액": 1000.0},
            {"구분": "AP", "만기일": pd.Timestamp("2026-10-01"), "원화금액": 1_300_000.0, "USD환산금액": 1000.0},
        ]
    )
    scenarios = [ScenarioInput(label="중앙값", rate=1350.0, source="test", is_base=True)]
    matrix = build_pnl_matrix(df, scenarios, REPORT_DATE)

    pivoted = pivot_pnl_matrix(matrix)
    assert not pivoted.empty

    forecast_df = samples_to_dataframe(MockForecastSource().fetch_samples("2026-08"))

    excel_bytes = build_excel_report(
        pnl_matrix=matrix,
        clean_df=df,
        quarantined_df=pd.DataFrame(),
        excluded_settled_df=pd.DataFrame(),
        forecast_df=forecast_df,
        manual_history_df=pd.DataFrame(),
    )
    assert isinstance(excel_bytes, bytes)
    assert excel_bytes[:2] == b"PK"  # xlsx는 zip 컨테이너
    assert len(excel_bytes) > 0
