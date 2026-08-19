"""화면/엑셀 전반에서 재사용하는 숫자 표기 규칙 (PRD §5 F5 — 3단계 UI 디자인 요구사항).

원화는 천단위 콤마, USD는 소수점 포함, 환율은 소수 2자리로 통일한다. 손익처럼
부호가 의미를 갖는 값은 색상에만 기대지 않도록 "+"/"-" 부호와 ▲/▼ 기호를 함께 붙인다
(dataviz 스킬: 색상 단독으로 의미를 전달하지 않는다).
"""
from __future__ import annotations

POSITIVE_COLOR = "#0ca30c"  # dataviz 스킬 palette.md status "good"
NEGATIVE_COLOR = "#d03b3b"  # dataviz 스킬 palette.md status "critical"
NEUTRAL_TEXT = "#31302c"  # 명시적 잉크색 — "inherit"는 캔버스 기반 그리드에서 무시/투명 처리될 수 있음


def fmt_krw(value: float) -> str:
    return f"{value:,.0f}"


def fmt_usd(value: float) -> str:
    return f"{value:,.2f}"


def fmt_rate(value: float) -> str:
    return f"{value:,.2f}"


def signed_arrow(value: float) -> str:
    if value > 0:
        return "▲"
    if value < 0:
        return "▼"
    return "‒"


def fmt_signed_krw(value: float) -> str:
    """부호(+/-)와 방향 기호(▲/▼)를 함께 붙인 원화 금액 — 색상이 안 보여도 뜻이 통하도록."""
    if value != value:  # NaN
        return "-"
    sign = "+" if value > 0 else ("-" if value < 0 else "")
    return f"{signed_arrow(value)} {sign}{abs(value):,.0f}"


def sign_color(value: float) -> str:
    """pandas Styler용 CSS color 문자열. 0/NaN은 기본 텍스트 색을 유지한다."""
    if value != value:
        return f"color: {NEUTRAL_TEXT}"
    if value > 0:
        return f"color: {POSITIVE_COLOR}"
    if value < 0:
        return f"color: {NEGATIVE_COLOR}"
    return f"color: {NEUTRAL_TEXT}"
