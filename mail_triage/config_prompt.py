from __future__ import annotations

from collections import Counter
from pathlib import Path

from .models import MailRecord

ROOT = Path(__file__).resolve().parent.parent

_TEMPLATE = """\
あなたはmail-triageプロジェクト(個人用Gmail自動仕分けツール)の設定ファイルを更新する作業を行います。
このプロンプトは、会話コンテキストが無い状態からでも作業できるように、必要な情報をまとめたものです。

## ツールの目的
Gmailに届く仕事・金融・EC等の雑多なメールを、送信元ドメインと件名パターンから自動分類し、
重要度区分(config.verdict_levelsで定義。現在は「重要」>「技術ニュース」>「要確認」>「確認不要」の4段階)を判定する。
ルールで判定しきれない場合のみAI(Jev)で判定する。「要確認」「確認不要」は表示上の2大項目そのもので、
それ以外の区分(重要,技術ニュースなど)はdisplay_groupで指定した側の大項目に統合表示され、バッジで区別される。

## 設定ファイルの場所とフォーマット
{root}\\config\\classification_rules.json
- version: 設定バージョン(数値)
- dry_run: true の間はGmailへの実書き込み(ラベル付与)を行わない
- jev_enabled: false にすると段階3(Jev)をスキップする(ルール整備中、Jev呼び出しを抑えたい時用)
- confidence_threshold: Jev判定の低確信度フラグを立てる閾値(0〜1)
- gmail_fetch: {{base_query}} — inbox取得条件(inbox内の対象を毎回全件取得する)
- sender_categories: [{{domain_regex, category}}, ...] — 送信元ドメインの正規表現 → カテゴリ(例: 仕事/金融/EC/技術/サービス/その他)
- verdict_levels: [{{name, display_group, apply_label, label_name(省略可)}}, ...] — 重要度区分の定義。
  配列の並び順=優先度(先頭が最優先、ルール競合時に採用される)。
  display_group は "要確認" か "確認不要" のどちらに統合表示するか。
  apply_label はGmailにラベルを付けるか。
  (既読化・inboxからの除外は設定ではなく、レポート画面の「一括既読・アーカイブ」ボタンでのみ行う)
  label_name を省略すると name がそのままGmailラベル名になるが、
  Gmailは"重要"のようにシステムラベルの表示名と衝突する名前でのラベル作成を拒否することがあるため、
  その場合はlabel_nameで実際に付けるラベル名だけ別名に上書きできる(現に"重要"はlabel_name:"重要メール"としている)。
  区分を増減したい場合はここに追加/削除するだけでよい(コード変更は不要)。
  ただし「要確認」「確認不要」の2つは削除不可(display_groupの受け皿そのものであるため)。
- importance_rules: [{{category, subject_regex, verdict}}, ...] — カテゴリ+件名正規表現 → verdict(verdict_levelsのnameのいずれか)
- jev_prompt: {{instructions, criteria}} — Jevに渡す判断基準(区分ごとの説明文)。
  パーソナライズしたい場合はここを編集する(コード変更は不要)。criteriaのキーはverdict_levelsのnameと完全一致させる必要がある
  (区分を追加/削除したら、jev_promptのcriteriaも同時に追加/削除すること)。

## 各設定を利用する処理と実装ファイル
- mail_triage/rule_classifier.py の classify_category() が sender_categories を参照し、カテゴリを決定する
- mail_triage/rule_classifier.py の classify_verdict() が importance_rules を参照し、重要度区分を決定する
  (複数ルールが競合した場合はverdict_levelsの並び順(優先度が高い順)で安全側を採用する)
- 上記で判定できなかった場合のみ mail_triage/jev_adapter.py の classify_verdict_by_jev() が
  jev_prompt の内容を使ってJevに1回の呼び出しで全区分から選択させる(choice型、区分数がいくつでも1回で済む)
- mail_triage/runner.py の apply_gmail_actions() が verdict_levels の apply_label に従って
  Gmailへのラベル付与を行う
- mail_triage/gmail_client.py の build_query() が gmail_fetch を参照してGmail検索クエリを組み立てる
- mail_triage/config_loader.py が起動時にこのファイルを読み込み・検証する(必須キー、verdict_levelsの整合性、正規表現の妥当性のチェック)

## 現在未分類のメール(このプロンプトを生成した瞬間に、ログ全体を現在のconfigで再判定した実際の値)
未分類件数: {unclassified_count}件
送信元ドメイン別内訳(件数の多い順、上位30):
{domain_summary}

この件数・内訳は生成時点でのその場計算なので、レポートHTML上に表示されている数値(生成タイミングやデータ範囲が異なる場合がある)より正確です。
詳細確認や個別のsender/subject/snippetを見たい場合は下記ディレクトリ配下の日次ログ(YYYY-MM-DD.jsonl)、または scripts/query_logs.py を使ってください。
{log_dir}
config/classification_rules.json の sender_categories に追記してください。

## 件数調査に使えるスクリプト(ルール追加前に必ず使うこと)
{root}\\scripts\\query_logs.py が、判定ログ全体(logs/配下の全日次JSONL)から
送信元ドメイン正規表現・件名正規表現・本文冒頭(snippet)正規表現・期間で
該当メール件数を調べられる。新しい sender_categories / importance_rules の
正規表現を追記する前に、必ずこのスクリプトで実際に何件ヒットするか確認すること
(誤って広すぎる正規表現を追加し、無関係なメールまで巻き込むのを防ぐため)。

使用例:
  python scripts/query_logs.py --sender-domain-regex "追加したいdomain_regex"
  python scripts/query_logs.py --subject-regex "追加したいsubject_regex" --since 2026-09-01
  python scripts/query_logs.py --sender-domain-regex "..." --json   # 該当レコードをJSONLでそのまま取得

--sender-domain-regex は config の domain_regex と同じ書き方・同じロジック(送信元アドレスのドメイン部分に対するre.search)で評価されるため、
config に書く正規表現の値をそのままこのオプションに渡して事前検証できる。
"""


def build_config_prompt(log_dir: Path, unclassified_records: list[MailRecord]) -> str:
    domain_counts = Counter(r.sender.rsplit("@", 1)[-1].lower() for r in unclassified_records)
    domain_summary = "\n".join(
        f"  {count:4d}件  {domain}" for domain, count in domain_counts.most_common(30)
    ) or "  (なし)"
    # 末尾に改行が残っていると、ターミナルに貼り付けた際にカーソルが空行に残り、
    # その後のEnterが送信ではなく改行として扱われてしまうことがあるため取り除く。
    return _TEMPLATE.format(
        root=ROOT,
        log_dir=log_dir,
        unclassified_count=len(unclassified_records),
        domain_summary=domain_summary,
    ).rstrip("\n")
