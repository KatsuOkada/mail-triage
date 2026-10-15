"""LAN 内の端末向けの Web サーバーを起動する(Raspberry Pi の systemd から常駐させる)。

環境変数:
  MAIL_TRIAGE_DATA_DIR      ログ(logs/)と Web の状態(web/)の置き場所。省略時はリポジトリ直下
  MAIL_TRIAGE_DASHBOARD_COPY  ダッシュボード用の要約を置くパス(同じ機械のダッシュボードに渡す)
  MAIL_TRIAGE_WEB_PORT      待ち受けるポート(省略時 8765)
"""
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from mail_triage.batch_runner import run_once
from mail_triage.gmail_client import bulk_mark_read_and_archive, get_service
from mail_triage.web_app import WebCore, serve

DATA_DIR = Path(os.environ.get("MAIL_TRIAGE_DATA_DIR", ROOT))
LOG_DIR = DATA_DIR / "logs"
CONFIG_PATH = ROOT / "config" / "classification_rules.json"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    def runner(progress):
        return run_once(get_service(), CONFIG_PATH, LOG_DIR, progress=progress)

    def archive(ids):
        return bulk_mark_read_and_archive(get_service(), ids)

    core = WebCore(DATA_DIR, LOG_DIR, CONFIG_PATH, runner)
    serve(core, archive, port=int(os.environ.get("MAIL_TRIAGE_WEB_PORT", "8765")))


if __name__ == "__main__":
    main()
