"""
本番用のバッチ実行スクリプト。夜間のタスクスケジューラ、または手動CLIから実行する。

処理内容:
1. 前回チェック時刻以降の新着メールを取得
2. Rule Classifier(段階1,2) → Jev Adapter(段階3)で分類
3. Gmailへ書き戻し(カテゴリラベル付与、確認不要なら既読化・アーカイブ)
   ※config.dry_run が true の間は実際の書き込みは行われない
4. 判定結果を日次JSONLに記録
5. 全て成功したら、今回の実行開始時刻を次回のチェックポイントとして保存
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from mail_triage.batch import fetch_new_records
from mail_triage.config_loader import load_config
from mail_triage.fetch_state import save_last_checked
from mail_triage.gmail_client import get_service
from mail_triage.runner import run

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"


def main() -> None:
    config = load_config(ROOT / "config" / "classification_rules.json")
    service = get_service()

    records, run_start = fetch_new_records(service, config)
    print(f"新着{len(records)}件を処理します(dry_run={config['dry_run']})。")

    processed = run(records, config, LOG_DIR, service=service)

    need_check = sum(1 for r in processed if r.verdict == "要確認")
    no_check = sum(1 for r in processed if r.verdict == "確認不要")
    unclassified = sum(1 for r in processed if r.category is None)
    low_conf = sum(1 for r in processed if r.low_confidence_flag)

    print(f"要確認: {need_check}件 / 確認不要: {no_check}件 / 未分類: {unclassified}件 / 低確信度: {low_conf}件")

    save_last_checked(run_start)
    print(f"次回チェックポイントを保存しました: {run_start.isoformat()}")


if __name__ == "__main__":
    main()
