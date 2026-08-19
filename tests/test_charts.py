"""F1 차트 스모크 테스트 — 카테고리 순서/색상 스케일이 build_maturity_buckets 결과와 어긋나지 않는지."""
import altair as alt
import pandas as pd

from src.charts import AP_COLOR, AR_COLOR, build_f1_chart
from src.maturity_view import BEYOND_WINDOW_BUCKET, OVERDUE_BUCKET, build_maturity_buckets


def test_build_f1_chart_returns_layered_chart_without_crashing():
    buckets = build_maturity_buckets(
        pd.DataFrame(
            [
                {"구분": "AR", "만기일": pd.Timestamp("2026-08-19"), "USD환산금액": 100.0},
                {"구분": "AP", "만기일": pd.Timestamp("2026-08-19"), "USD환산금액": 40.0},
            ]
        ),
        report_date=pd.Timestamp("2026-08-19").date(),
    )
    chart = build_f1_chart(buckets)
    assert isinstance(chart, alt.LayerChart)


def test_chart_x_axis_sort_matches_bucket_row_order_not_alphabetical():
    """dataviz 스킬: 카테고리 순서는 라이브러리 기본 정렬에 맡기지 않고 명시적으로 고정한다."""
    buckets = build_maturity_buckets(
        pd.DataFrame([{"구분": "AR", "만기일": pd.Timestamp("2026-08-19"), "USD환산금액": 1.0}]),
        report_date=pd.Timestamp("2026-08-19").date(),
    )
    chart = build_f1_chart(buckets)
    bar_layer = chart.layer[0]
    sort_order = bar_layer.encoding.x["sort"]
    assert sort_order[0] == OVERDUE_BUCKET
    assert sort_order[-1] == BEYOND_WINDOW_BUCKET
    assert sort_order == list(buckets["만기월"])


def test_ar_ap_color_scale_uses_fixed_categorical_order_not_cycled():
    buckets = build_maturity_buckets(
        pd.DataFrame([{"구분": "AR", "만기일": pd.Timestamp("2026-08-19"), "USD환산금액": 1.0}]),
        report_date=pd.Timestamp("2026-08-19").date(),
    )
    chart = build_f1_chart(buckets)
    bar_layer = chart.layer[0]
    color_scale = bar_layer.encoding.color["scale"]
    assert color_scale.domain == ["AR", "AP"]
    assert color_scale.range == [AR_COLOR, AP_COLOR]
