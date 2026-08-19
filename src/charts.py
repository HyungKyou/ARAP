"""F1 만기월별 AR/AP 차트 (PRD §5 F1) — dataviz 스킬 가이드 적용.

- AR/AP는 색상으로 구분되는 진짜 "카테고리"이므로 categorical 색(고정 순서, 인접쌍 CVD
  검증됨: dataviz 스킬 palette.md 기본 팔레트의 슬롯1/슬롯2)을 쓴다.
- Net(AR-AP)은 파생 지표이지 별도 카테고리가 아니므로 카테고리 색을 새로 쓰지 않고
  중립 잉크색 점선 + 직접 라벨로 표시한다 (범례 슬롯을 늘리지 않음).
- 막대는 나란히(grouped) 배치한다 — 누적(stacked)이면 "AR이 얼마인지"를 막대 높이만으로
  읽을 수 없어 PRD §5 F1의 취지(만기월별 AR/AP 규모 비교)에 맞지 않는다.
- x축 정렬은 build_maturity_buckets()가 만든 시간순(과거→현재→미래)을 그대로 강제한다
  (차트 라이브러리 기본 정렬에 맡기면 알파벳/사전순으로 흐트러짐).
"""
from __future__ import annotations

import altair as alt
import pandas as pd

AR_COLOR = "#2a78d6"
AP_COLOR = "#eb6834"
NET_INK = "#31302c"


def build_f1_chart(
    buckets: pd.DataFrame, visible_series: tuple[str, ...] = ("AR", "AP", "Net")
) -> alt.LayerChart:
    """만기월별 AR/AP(+Net) 차트. `visible_series`로 AR/AP/Net을 선택적으로 표시할 수 있다."""
    category_order = list(buckets["만기월"])
    bar_series = [s for s in ("AR", "AP") if s in visible_series]

    layers = []

    if bar_series:
        long_df = buckets.melt(id_vars="만기월", value_vars=bar_series, var_name="구분", value_name="금액")
        bars = (
            alt.Chart(long_df)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, size=18)
            .encode(
                x=alt.X("만기월:N", sort=category_order, title="만기월", axis=alt.Axis(labelAngle=-40)),
                xOffset=alt.XOffset("구분:N", sort=bar_series),
                y=alt.Y("금액:Q", title="USD 환산금액"),
                color=alt.Color(
                    "구분:N",
                    sort=["AR", "AP"],
                    scale=alt.Scale(domain=["AR", "AP"], range=[AR_COLOR, AP_COLOR]),
                    legend=alt.Legend(title=None, orient="top"),
                ),
                tooltip=[
                    alt.Tooltip("만기월:N", title="만기월"),
                    alt.Tooltip("구분:N", title="구분"),
                    alt.Tooltip("금액:Q", title="USD 환산금액", format=",.0f"),
                ],
            )
        )
        layers.append(bars)

    if "Net" in visible_series:
        net_line = (
            alt.Chart(buckets)
            .mark_line(
                color=NET_INK,
                strokeWidth=2,
                strokeDash=[5, 3],
                point=alt.OverlayMarkDef(size=50, filled=True, color=NET_INK),
            )
            .encode(
                x=alt.X("만기월:N", sort=category_order),
                y=alt.Y("Net:Q", title="USD 환산금액" if not bar_series else None),
                tooltip=[
                    alt.Tooltip("만기월:N", title="만기월"),
                    alt.Tooltip("Net:Q", title="Net (AR-AP)", format=",.0f"),
                ],
            )
        )
        net_label = (
            alt.Chart(buckets.iloc[[-1]])
            .mark_text(align="left", dx=8, dy=-6, color=NET_INK, fontWeight="bold")
            .encode(x=alt.X("만기월:N", sort=category_order), y="Net:Q", text=alt.value("Net (AR−AP)"))
        )
        layers.extend([net_line, net_label])

    if not layers:
        # 아무것도 선택되지 않은 극단적인 경우에도 빈 축이라도 그려서 화면이 깨지지 않게 한다.
        layers.append(
            alt.Chart(buckets).mark_bar(opacity=0).encode(x=alt.X("만기월:N", sort=category_order), y="AR:Q")
        )

    chart = layers[0]
    for layer in layers[1:]:
        chart = chart + layer
    return chart.resolve_scale(y="shared").properties(height=380)
