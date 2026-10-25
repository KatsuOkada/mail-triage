import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import apply_schedule  # noqa: E402


def _write(tmp_path, data):
    path = tmp_path / "schedule.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_repository_schedule_is_valid():
    assert apply_schedule.load_run_times() == ["05:00", "12:00", "18:00"]


def test_load_run_times_sorts_and_dedupes(tmp_path):
    path = _write(tmp_path, {"run_times": ["18:00", "05:00", "18:00"]})
    assert apply_schedule.load_run_times(path) == ["05:00", "18:00"]


@pytest.mark.parametrize("times", [[], ["5:00"], ["24:00"], ["12:60"], [1200], None])
def test_load_run_times_rejects_bad_times(tmp_path, times):
    with pytest.raises(ValueError):
        apply_schedule.load_run_times(_write(tmp_path, {"run_times": times}))


def test_timer_override_replaces_calendar():
    text = apply_schedule.timer_override(["05:00", "12:00"])
    lines = text.splitlines()
    assert lines.index("OnCalendar=") < lines.index("OnCalendar=*-*-* 05:00:00")
    assert "OnCalendar=*-*-* 12:00:00" in lines
    assert "Description=mail-triage を定時(05:00, 12:00)に実行" in lines
