"""F3-2 수동 입력 저장/이력/시나리오 변환 검증."""
from datetime import datetime

from src.manual_input import (
    MAX_MANUAL_ENTRIES,
    ManualRateEntry,
    append_history,
    load_history,
    manual_entries_to_scenarios,
)


def test_append_and_load_history_roundtrip(tmp_path):
    path = tmp_path / "history.json"
    entry = ManualRateEntry(rate=1370.5, entered_by="홍길동", entered_at=datetime(2026, 8, 19, 10, 0))
    append_history(entry, path=path)

    loaded = load_history(path)
    assert len(loaded) == 1
    assert loaded[0].rate == 1370.5
    assert loaded[0].entered_by == "홍길동"


def test_append_history_accumulates(tmp_path):
    path = tmp_path / "history.json"
    for i in range(3):
        append_history(
            ManualRateEntry(rate=1300.0 + i, entered_by="A", entered_at=datetime(2026, 8, 19, 10, i)),
            path=path,
        )
    assert len(load_history(path)) == 3


def test_load_history_missing_file_returns_empty(tmp_path):
    assert load_history(tmp_path / "does_not_exist.json") == []


def test_manual_entries_to_scenarios_caps_at_max():
    entries = [
        ManualRateEntry(rate=1300.0 + i, entered_by="A", entered_at=datetime(2026, 8, 19, 10, i))
        for i in range(MAX_MANUAL_ENTRIES + 3)
    ]
    scenarios = manual_entries_to_scenarios(entries)
    assert len(scenarios) == MAX_MANUAL_ENTRIES
    assert all(not s.is_base for s in scenarios)
    assert "수동 입력" in scenarios[0].source
