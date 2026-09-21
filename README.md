# mail-triage

Gmailの新着メールを夜間バッチで分類し、朝Obsidianノートとして確認できるようにする個人用ツール。

設計の詳細は要件定義・アーキテクチャ設計ドキュメントを参照。

## セットアップ

```
cp .env.example .env
# .env に OPENROUTER_API_KEY / TYPESAFE_API_KEY を設定
pip install -r requirements.txt
```

## ディレクトリ構成

- `mail_triage/` — 分類ロジック本体(Config Loader / Rule Classifier / Jev Adapter / Decision Logger)
- `config/classification_rules.json` — 送信元カテゴリ・重要度ルールの設定
- `tests/` — 単体テスト
- `scripts/` — 検証用スクリプト

個人が自分のGmailアカウントに対してのみ使うツールです。プライバシーポリシーは[PRIVACY.md](./PRIVACY.md)を参照。
