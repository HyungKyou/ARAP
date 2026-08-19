"""F3-2. 수동 환율 입력 — 저장/이력 관리 (PRD §5 F3-2, §7 추적성).

F3(AI 자동수집)이 지연·실패하더라도 담당자가 항상 쓸 수 있어야 하는 경로이므로
AI 수집 로직과 완전히 독립적으로 동작한다. 입력 이력은 세션이 끝나도 남아있도록
로컬 JSON 파일에 append 방식으로 저장한다 (감사 추적용).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .pnl_engine import ScenarioInput

MAX_MANUAL_ENTRIES = 5

DEFAULT_HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "manual_rate_history.json"


@dataclass(frozen=True)
class ManualRateEntry:
    rate: float
    entered_at: datetime
    entered_by: str = "-"  # 담당자 요청으로 UI에서 입력자 필드를 없앰 — 있으면 쓰고, 없으면 "-"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entered_at"] = self.entered_at.isoformat()
        return d

    @staticmethod
    def from_dict(d: dict) -> "ManualRateEntry":
        return ManualRateEntry(
            rate=d["rate"],
            entered_at=datetime.fromisoformat(d["entered_at"]),
            entered_by=d.get("entered_by", "-"),
        )


def load_history(path: Path = DEFAULT_HISTORY_PATH) -> list[ManualRateEntry]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return [ManualRateEntry.from_dict(d) for d in raw]


def append_history(entry: ManualRateEntry, path: Path = DEFAULT_HISTORY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    history = load_history(path)
    history.append(entry)
    with path.open("w", encoding="utf-8") as f:
        json.dump([e.to_dict() for e in history], f, ensure_ascii=False, indent=2)


def manual_entries_to_scenarios(entries: list[ManualRateEntry]) -> list[ScenarioInput]:
    """F4 매트릭스에 넣을 수 있도록 ScenarioInput으로 변환. 최대 5개까지만 반영."""
    limited = entries[:MAX_MANUAL_ENTRIES]
    scenarios = []
    for i, e in enumerate(limited):
        who = f", {e.entered_by}" if e.entered_by and e.entered_by != "-" else ""
        scenarios.append(
            ScenarioInput(
                label=f"수동입력{i + 1}",
                rate=e.rate,
                source=f"수동 입력 ({e.entered_at:%Y-%m-%d %H:%M}{who})",
                is_base=False,
            )
        )
    return scenarios
