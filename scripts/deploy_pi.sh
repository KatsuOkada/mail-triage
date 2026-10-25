#!/bin/bash
# 開発PC(Git Bash)から Raspberry Pi の ~/mail-triage にプログラムを配置して、Web サーバーを再起動する。
# あわせて config/schedule.json の実行時刻を、定時実行のタイマー(mail-triage-nightly.timer)に反映する。
# 配置するのは git の追跡対象と、まだ追跡していない新しいファイルだけ(.gitignore の秘密情報・個人設定・ログは送らない)。
set -euo pipefail
cd "$(dirname "$0")/.."
HOST="${1:?使い方: bash scripts/deploy_pi.sh <ssh のホスト名>}"
git ls-files -co --exclude-standard -z | tar --null -T - -cf - | ssh "$HOST" 'mkdir -p ~/mail-triage && tar -xf - -C ~/mail-triage'
ssh "$HOST" 'cd ~/mail-triage && .venv/bin/pip install -q -r requirements.txt && sudo systemctl restart mail-triage-web && systemctl is-active mail-triage-web'
ssh "$HOST" 'cd ~/mail-triage && .venv/bin/python scripts/apply_schedule.py > /tmp/mail-triage-schedule.conf   && sudo install -D -m 644 /tmp/mail-triage-schedule.conf /etc/systemd/system/mail-triage-nightly.timer.d/schedule.conf   && rm /tmp/mail-triage-schedule.conf && sudo systemctl daemon-reload && sudo systemctl restart mail-triage-nightly.timer   && systemctl list-timers mail-triage-nightly.timer --no-pager'
