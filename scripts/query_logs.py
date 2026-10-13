"""
判定ログ(logs/YYYY-MM-DD.jsonl)から条件に合うメールを抽出・件数集計するCLIツール。
送信元ドメイン・件名・本文冒頭(snippet)の正規表現、期間で絞り込める。

使用例:
  # 特定ドメインからのメールが何件あるか調べる
  python scripts/query_logs.py --sender-domain-regex "example-shop\\.com$"

  # 2026-09-15以降で件名に「セキュリティ通知」を含むメールを一覧
  python scripts/query_logs.py --subject-regex "セキュリティ通知" --since 2026-09-15

  # 後続処理(Claudeでの設定更新など)向けにJSONLでそのまま出力する
  python scripts/query_logs.py --sender-domain-regex "example-cloud\\.com$" --json
"""
import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.stdout is not None:  # pythonw.exe経由で起動された場合、stdoutがNoneになりうるため
    sys.stdout.reconfigure(encoding="utf-8")

from mail_triage.log_query import iter_decision_log_records, query_records

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = ROOT / "logs"


def _parse_datetime_arg(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def main() -> None:
    parser = argparse.ArgumentParser(description="判定ログから条件に合うメールを抽出・件数集計する")
    parser.add_argument("--sender-domain-regex", help="送信元ドメインに対する正規表現(config同様の書き方)")
    parser.add_argument("--subject-regex", help="件名に対する正規表現")
    parser.add_argument("--snippet-regex", help="本文冒頭(snippet)に対する正規表現")
    parser.add_argument("--since", help="この日時以降(YYYY-MM-DD または YYYY-MM-DDTHH:MM)")
    parser.add_argument("--until", help="この日時以前(YYYY-MM-DD または YYYY-MM-DDTHH:MM)")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="判定ログのディレクトリ(既定: logs/)")
    parser.add_argument("--limit", type=int, default=50, help="一覧表示する件数の上限(既定: 50。--jsonでは無効)")
    parser.add_argument("--json", action="store_true", help="一致したレコードをJSONL形式でそのまま出力する")
    args = parser.parse_args()

    records = iter_decision_log_records(args.log_dir)
    matched = query_records(
        records,
        sender_domain_regex=args.sender_domain_regex,
        subject_regex=args.subject_regex,
        snippet_regex=args.snippet_regex,
        since=_parse_datetime_arg(args.since),
        until=_parse_datetime_arg(args.until),
    )

    if args.json:
        for record in matched:
            print(json.dumps(asdict(record), ensure_ascii=False))
        return

    print(f"該当件数: {len(matched)}件")
    for record in matched[: args.limit]:
        print("-" * 40)
        print(f"{record.date} | {record.sender}")
        print(f"件名: {record.subject}")
        print(f"category={record.category} verdict={record.verdict}")
    if len(matched) > args.limit:
        print(f"... 他{len(matched) - args.limit}件(--limitで表示件数を変更、--jsonで全件出力できます)")


if __name__ == "__main__":
    main()
