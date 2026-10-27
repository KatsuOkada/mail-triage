# mail-triage

Gmailの新着メールを夜間バッチで分類し、朝Obsidianノートとして確認できるようにする個人用ツール。

設計の詳細は要件定義・アーキテクチャ設計ドキュメントを参照。

## セットアップ

```
cp .env.example .env
# .env に OPENROUTER_API_KEY / TYPESAFE_API_KEY を設定
cp config/classification_rules.example.json config/classification_rules.json
# 自分の送信元ドメインや重要度ルールに書き換える(このファイルはgit管理外)
pip install -r requirements.txt
```

## 実行方法

- `python scripts/run_batch.py` — inbox全件を1回分類し、レポートを書き出す(タスクスケジューラ向け)
- `python scripts/serve_report.py` — 直近のレポートをレビュー用ローカルサーバーで表示する
- `python scripts/tray.py` — タスクトレイに常駐し、実行結果の表示・手動実行・Jev利用/ドライモードの切り替えをアイコンメニューから行える

## 判定の流れ

1. 送信元ドメイン → カテゴリ(`sender_categories`)
2. カテゴリ × 件名の正規表現 → 重要度区分(`importance_rules`)。**上に書いた行が優先**(先勝ち)なので、例外の行は一律の行(`.*`)より上に書く。`verdict` に `"Jevで確認"` と書いた行に当たったメールは、ここでは決めずに 3 に回す
3. 2 で決まらなかったメールは Jev で判定する(`jev_prompt`)。どの行にも当たらなかったメール・未分類のメールは件名と snippet だけを渡す。`"Jevで確認"` に当たったメールだけは本文も取得して渡す。本文は HTML から画面に表示される文字だけを取り出し(style・script・head・`display:none` の要素は除き、見えない文字を消し、空白をまとめる)、`jev_body.redact_regexes` に当たる部分を「＊」にして、先頭の `jev_body.max_chars` 文字(既定 500 文字)だけを送る。本文は判定ログには残さない

## ディレクトリ構成

- `mail_triage/` — 分類ロジック本体(Config Loader / Rule Classifier / Jev Adapter / Decision Logger)
- `config/classification_rules.example.json` — 送信元カテゴリ・重要度ルールの設定のサンプル(実際の設定 `config/classification_rules.json` はgit管理外)
- `tests/` — 単体テスト
- `scripts/` — 検証用スクリプト

個人が自分のGmailアカウントに対してのみ使うツールです。プライバシーポリシーは[PRIVACY.md](./PRIVACY.md)を参照。
