"""
run_batch.pyが書き出したレポート(logs/YYYY-MM-DD_HHMMSS_report.html)を
ローカルサーバーで表示する。要確認/確認不要/(あれば)Jev判断対象の一覧に加えて、
「確認不要を一括既読・アーカイブ」「未分類をClaudeで設定更新」ボタンを提供する。

使い方:
  python scripts/serve_report.py                    # 最新のレポートを表示
  python scripts/serve_report.py 2026-09-22_143022_report.html  # 指定のレポートを表示
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.stdout is not None:  # pythonw.exe経由で起動された場合、stdoutがNoneになりうるため
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from mail_triage.gmail_client import get_service
from mail_triage.report_server import serve_report

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"


def find_latest_report(log_dir: Path) -> Path:
    reports = sorted(log_dir.glob("*_report.html"))
    if not reports:
        raise SystemExit("レポートファイルが見つかりません。先に scripts/run_batch.py を実行してください。")
    return reports[-1]


def main() -> None:
    report_html_path = LOG_DIR / sys.argv[1] if len(sys.argv) > 1 else find_latest_report(LOG_DIR)
    if not report_html_path.exists():
        raise SystemExit(f"レポートファイルが見つかりません: {report_html_path}")

    service = get_service()
    serve_report(service, report_html_path, LOG_DIR)


if __name__ == "__main__":
    main()
