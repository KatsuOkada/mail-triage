"""
本番用のバッチ実行スクリプト。夜間のタスクスケジューラ、または手動CLIから実行する。

処理内容:
1. inbox内の対象メールを全件取得(処理後はinboxから片付けていく運用のためチェックポイントは使わない)
2. Rule Classifier(段階1,2) → jev_enabledがtrueならJev Adapter(段階3)で分類
3. Gmailへ書き戻し(カテゴリラベル付与、重要度区分ごとのラベル付与・既読化アーカイブはconfig.verdict_levelsに従う)
   ※config.dry_run が true の間は実際の書き込みは行われない
4. 判定結果を日次JSONLに記録
5. レビュー用のHTMLレポートを実行時刻付きのファイル名で書き出す(1日に何度実行しても上書きされない)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# pythonw.exe(コンソール無しでの無人実行)ではsys.stdoutがNoneになるため、
# reconfigure()を呼ぶとその時点でAttributeErrorになりログすら残らず落ちる。ここで防ぐ。
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from mail_triage.batch_runner import run_once
from mail_triage.gmail_client import get_service

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = Path(os.environ.get("MAIL_TRIAGE_DATA_DIR", ROOT)) / "logs"
CONFIG_PATH = ROOT / "config" / "classification_rules.json"


def main() -> None:
    service = get_service()
    run_once(service, CONFIG_PATH, LOG_DIR)


if __name__ == "__main__":
    main()
