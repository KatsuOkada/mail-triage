"""
mail-triageをタスクトレイ常駐アプリとして起動する。

タスクトレイアイコンを右クリックすると:
- 実行結果を表示: 直近のレポートをブラウザで開く(レビュー用サーバーも同時に起動している)
- 手動実行: その場でinbox全件を処理し、結果を表示する
- Jev利用 / ドライモード: それぞれON/OFFを切り替える(config/classification_rules.jsonを直接書き換える)
- 終了: サーバーとトレイアイコンを両方停止する

使い方:
  python scripts/tray.py            # 通常起動(既存の最新レポートを表示できる状態で待機)
  python scripts/tray.py --run-now  # 起動直後に1回自動実行し、完了後にブラウザで結果を開く
                                     # (タスクスケジューラでの定時実行用)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# pythonw.exe(タスクスケジューラでの無人実行用、コンソール無し)ではsys.stdoutがNoneになるため、
# reconfigure()を呼ぶとその時点でAttributeErrorになりログすら残らず落ちる。ここで防ぐ。
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from mail_triage.gmail_client import get_service
from mail_triage.tray_app import run_tray_app

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
CONFIG_PATH = ROOT / "config" / "classification_rules.json"


def find_latest_report(log_dir: Path) -> Path | None:
    reports = sorted(log_dir.glob("*_report.html"))
    return reports[-1] if reports else None


def main() -> None:
    auto_run_on_start = "--run-now" in sys.argv[1:]
    service = get_service()
    initial_report_path = find_latest_report(LOG_DIR)
    run_tray_app(service, CONFIG_PATH, LOG_DIR, initial_report_path, auto_run_on_start=auto_run_on_start)


if __name__ == "__main__":
    main()
