#!/bin/bash
# 開発PC(Git Bash)から Raspberry Pi の ~/mail-triage にプログラムを配置して、Web サーバーを再起動する。
# 配置するのは git の追跡対象と、まだ追跡していない新しいファイルだけ(.gitignore の秘密情報・個人設定・ログは送らない)。
set -euo pipefail
cd "$(dirname "$0")/.."
HOST="${1:-raspi}"
git ls-files -co --exclude-standard -z | tar --null -T - -cf - | ssh "$HOST" 'mkdir -p ~/mail-triage && tar -xf - -C ~/mail-triage'
ssh "$HOST" 'cd ~/mail-triage && .venv/bin/pip install -q -r requirements.txt && sudo systemctl restart mail-triage-web && systemctl is-active mail-triage-web'
