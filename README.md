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

## ディレクトリ構成

- `mail_triage/` — 分類ロジック本体(Config Loader / Rule Classifier / Jev Adapter / Decision Logger)
- `config/classification_rules.example.json` — 送信元カテゴリ・重要度ルールの設定のサンプル(実際の設定 `config/classification_rules.json` はgit管理外)
- `tests/` — 単体テスト
- `scripts/` — 検証用スクリプト

個人が自分のGmailアカウントに対してのみ使うツールです。プライバシーポリシーは[PRIVACY.md](./PRIVACY.md)を参照。
