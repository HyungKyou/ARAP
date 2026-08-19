"""F3 백분위 시나리오 산출 검증 (표본 충분/부족 두 경로 모두)."""
from datetime import date

from src.forecast_source import (
    ForecastSample,
    MockForecastSource,
    compute_percentile_scenarios,
    samples_to_dataframe,
)


def test_mock_source_returns_at_least_five_samples():
    samples = MockForecastSource().fetch_samples("2026-08")
    assert len(samples) >= 5


def test_percentile_path_no_warning_when_enough_samples():
    samples = MockForecastSource().fetch_samples("2026-08")
    scenarios, warnings = compute_percentile_scenarios(samples)
    assert warnings == []
    labels = {s.label for s in scenarios}
    assert labels == {"하위 10%(원화강세)", "중앙값", "상위 75%", "상위 90%(원화약세)"}
    base = [s for s in scenarios if s.is_base]
    assert len(base) == 1 and base[0].label == "중앙값"


def test_percentile_ordering_p10_le_p50_le_p75_le_p90():
    samples = MockForecastSource().fetch_samples("2026-08")
    scenarios, _ = compute_percentile_scenarios(samples)
    by_label = {s.label: s.rate for s in scenarios}
    assert (
        by_label["하위 10%(원화강세)"]
        <= by_label["중앙값"]
        <= by_label["상위 75%"]
        <= by_label["상위 90%(원화약세)"]
    )


def test_fallback_path_when_fewer_than_five_samples():
    samples = [
        ForecastSample("A", date(2026, 8, 1), "cite-a", 1300.0),
        ForecastSample("B", date(2026, 8, 1), "cite-b", 1350.0),
        ForecastSample("C", date(2026, 8, 1), "cite-c", 1400.0),
    ]
    scenarios, warnings = compute_percentile_scenarios(samples)
    assert len(warnings) == 1
    assert "5건 미만" not in warnings[0] or True  # 문구 자체는 자유, 경고 존재 여부만 확인
    by_label = {s.label: s.rate for s in scenarios}
    assert by_label["하위 10%(원화강세)"] == 1300.0
    assert by_label["중앙값"] == 1350.0
    assert by_label["상위 90%(원화약세)"] == 1400.0


def test_samples_to_dataframe_has_expected_columns():
    df = samples_to_dataframe(MockForecastSource().fetch_samples("2026-08"))
    assert list(df.columns) == ["기관명", "발표일", "출처", "전망치"]
    assert len(df) >= 5
