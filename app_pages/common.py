"""페이지 여러 곳에서 쓰는 아주 작은 표시용 헬퍼. 계산 로직은 여기 두지 않는다."""
from __future__ import annotations

from src.pnl_engine import ScenarioInput


def scenario_icon(scenario: ScenarioInput) -> str:
    return "🖊️" if scenario.source.startswith("수동 입력") else "🤖"


def display_label(scenario: ScenarioInput) -> str:
    return f"{scenario_icon(scenario)} {scenario.label}"
