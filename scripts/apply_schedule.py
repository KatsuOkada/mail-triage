"""config/schedule.json の実行時刻から、Raspberry Pi の systemd タイマーの上書き設定を作る。

deploy_pi.sh が Pi の上で実行し、出力を
/etc/systemd/system/mail-triage-nightly.timer.d/schedule.conf に置く。
時刻を変えるときは、開発PC で config/schedule.json を直して deploy_pi.sh で配置する。

使い方:
  python scripts/apply_schedule.py   上書き設定を標準出力に出す(時刻が正しくなければ終了コード 1)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEDULE_PATH = ROOT / "config" / "schedule.json"
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def load_run_times(path: Path = SCHEDULE_PATH) -> list[str]:
    """実行時刻("HH:MM")の一覧を、重複を除いて早い順に返す。正しくなければ ValueError。"""
    times = json.loads(path.read_text(encoding="utf-8")).get("run_times")
    if not isinstance(times, list) or not times:
        raise ValueError("run_times に1つ以上の時刻を書いてください(例: [\"05:00\"])。")
    bad = [t for t in times if not isinstance(t, str) or not TIME_RE.match(t)]
    if bad:
        raise ValueError(f"時刻は \"HH:MM\"(00:00〜23:59)で書いてください: {bad}")
    return sorted(set(times))


def timer_override(times: list[str]) -> str:
    lines = [
        "# config/schedule.json から scripts/apply_schedule.py で作る。直接は直さない",
        "[Unit]",
        f"Description=mail-triage を定時({', '.join(times)})に実行",
        "",
        "[Timer]",
        "OnCalendar=",  # 元のユニットの時刻を消してから足す
        *(f"OnCalendar=*-*-* {t}:00" for t in times),
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
        times = load_run_times()
    except (OSError, ValueError) as e:
        print(f"config/schedule.json を読めません: {e}", file=sys.stderr)
        return 1
    sys.stdout.write(timer_override(times))
    return 0


if __name__ == "__main__":
    sys.exit(main())
