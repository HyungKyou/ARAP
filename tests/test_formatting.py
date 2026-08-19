"""3단계 표시 규칙(부호/화살표/색상) 검증 — 색상에만 의존하지 않는지가 핵심."""
import math

from src.formatting import fmt_krw, fmt_signed_krw, fmt_usd, sign_color, signed_arrow


def test_fmt_krw_uses_thousands_separator_no_decimals():
    assert fmt_krw(1234567.8) == "1,234,568"


def test_fmt_usd_keeps_two_decimals():
    assert fmt_usd(1234.5) == "1,234.50"


def test_signed_arrow_directions():
    assert signed_arrow(100) == "▲"
    assert signed_arrow(-100) == "▼"
    assert signed_arrow(0) == "‒"


def test_fmt_signed_krw_always_carries_a_sign_glyph_not_just_color():
    assert fmt_signed_krw(50_000).startswith("▲ +")
    assert fmt_signed_krw(-50_000).startswith("▼ -")
    assert fmt_signed_krw(0).startswith("‒")
    assert fmt_signed_krw(float("nan")) == "-"


def test_sign_color_matches_value_sign():
    assert sign_color(100) != sign_color(-100)
    assert "inherit" not in sign_color(0)  # 캔버스 그리드에서 무시될 수 있는 값은 쓰지 않는다
    assert "inherit" not in sign_color(float("nan"))
