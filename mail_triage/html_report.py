from __future__ import annotations

import html
import json
from typing import Any


# 区分バッジの色。未知の区分(configで新設された場合)はデフォルト色を使う。
_TIER_BADGE_COLORS = {
    "重要": "#c0392b",
    "技術ニュース": "#2874a6",
}
_DEFAULT_TIER_BADGE_COLOR = "#8a6d00"


def _render_mail_item(e: dict[str, Any]) -> str:
    tier_badge = e["tier_badge"]
    badge_html = ""
    if tier_badge:
        color = _TIER_BADGE_COLORS.get(tier_badge, _DEFAULT_TIER_BADGE_COLOR)
        badge_html = f'<span class="tier-badge" style="background:{color}">{html.escape(tier_badge)}</span> '
    return (
        '<li class="mail-item">'
        f'<span class="mail-title">{badge_html}'
        f'<a href="{html.escape(e["gmail_url"])}" target="_blank">{html.escape(e["subject"])}</a>'
        f' <span class="sender">({html.escape(e["sender"])})</span></span>'
        f'<span class="source-badge">{html.escape(e["source_label"])}</span>'
        "</li>"
    )


def _render_mail_list(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return '<p class="empty">(なし)</p>'
    items = "\n".join(_render_mail_item(e) for e in entries)
    return f"<ul>\n{items}\n</ul>"


def _render_categorized(section: dict[str, list[dict[str, Any]]]) -> str:
    if not section:
        return '<p class="empty">(なし)</p>'
    return "".join(
        f"<h3>{html.escape(category)}({len(entries)}件)</h3>{_render_mail_list(entries)}"
        for category, entries in section.items()
    )


def render_html(report: dict[str, Any], for_date: str) -> str:
    no_check_ids = [e["message_id"] for entries in report["確認不要"].values() for e in entries]
    unclassified_count = report["unclassified_count"]

    jev_pending_count = sum(len(entries) for entries in report["Jev判断対象"].values())
    jev_pending_section = (
        f"<h2>Jev判断対象</h2>{_render_categorized(report['Jev判断対象'])}"
        if jev_pending_count > 0
        else ""
    )

    need_check_html = _render_categorized(report["要確認"])
    no_check_html = _render_categorized(report["確認不要"])

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>メール仕分け結果 {html.escape(for_date)}</title>
<style>
 body {{ font-family: sans-serif; max-width: 720px; margin: 2em auto; line-height: 1.6; padding: 0 1em; }}
 h2 {{ border-bottom: 2px solid #ccc; padding-bottom: .2em; }}
 h3 {{ color: #555; margin-bottom: .2em; }}
 .sender {{ color: #888; font-size: .85em; }}
 .empty {{ color: #aaa; }}
 .mail-item {{ display: flex; justify-content: space-between; align-items: baseline; gap: 1em; }}
 .source-badge {{ flex-shrink: 0; font-size: .8em; color: #667; white-space: nowrap; }}
 .tier-badge {{ color: #fff; font-size: .75em; padding: .1em .5em; border-radius: 3px; margin-right: .4em; white-space: nowrap; }}
 button {{ margin-top: 1em; padding: .6em 1.2em; font-size: 1em; cursor: pointer; }}
 button:disabled {{ opacity: .5; cursor: default; }}
 #status {{ margin-top: .5em; color: #2a7; min-height: 1.5em; }}
</style>
</head>
<body>
<h1>メール仕分け結果({html.escape(for_date)})</h1>

<h2>要確認</h2>
{need_check_html}

<h2>確認不要</h2>
{no_check_html}
<button id="bulk-archive-btn" onclick="bulkArchive()">一括既読・アーカイブ({len(no_check_ids)}件)</button>

{jev_pending_section}

<div>
<button id="config-btn" onclick="launchClaudeConfig()">未分類メールの設定ファイルを更新する({unclassified_count}件)</button>
<button id="open-config-btn" onclick="openConfigFile()">設定ファイルを開く</button>
</div>

<div id="status"></div>

<script>
const NO_CHECK_IDS = {json.dumps(no_check_ids, ensure_ascii=False)};

// サーバーが1リクエストずつしか処理できない作りのため、片方の処理中はもう片方のボタンも
// 押せないようにして、リクエストが重なって詰まることを防ぐ。
function setButtonsBusy(busy) {{
  document.getElementById("bulk-archive-btn").disabled = busy;
  document.getElementById("config-btn").disabled = busy;
  document.getElementById("open-config-btn").disabled = busy;
}}

async function openConfigFile() {{
  const status = document.getElementById("status");
  setButtonsBusy(true);
  status.textContent = "設定ファイルを開いています...";
  try {{
    const res = await fetch("/actions/open_config", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: "{{}}",
    }});
    const data = await res.json();
    status.textContent = data.ok
      ? `設定ファイルを${{data.editor}}で開きました。`
      : `エラー: ${{data.error}}`;
  }} catch (e) {{
    status.textContent = "エラー: " + e;
  }} finally {{
    setButtonsBusy(false);
  }}
}}

async function bulkArchive() {{
  const status = document.getElementById("status");
  if (NO_CHECK_IDS.length === 0) {{
    status.textContent = "対象のメールがありません。";
    return;
  }}
  setButtonsBusy(true);
  status.textContent = "処理中...";
  try {{
    const res = await fetch("/actions/bulk_archive", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{message_ids: NO_CHECK_IDS}}),
    }});
    const data = await res.json();
    if (!data.ok) {{
      status.textContent = `エラー: ${{data.error}}`;
    }} else if (data.failed_count > 0) {{
      status.textContent = `完了: ${{data.count}}件をアーカイブしました(${{data.failed_count}}件は失敗したため、そのままinboxに残っています。再度ボタンを押すと再試行できます)。`;
    }} else {{
      status.textContent = `完了: ${{data.count}}件をアーカイブしました。`;
    }}
  }} catch (e) {{
    status.textContent = "エラー: " + e;
  }} finally {{
    setButtonsBusy(false);
  }}
}}

async function launchClaudeConfig() {{
  const status = document.getElementById("status");
  setButtonsBusy(true);
  status.textContent = "準備中...(サーバー側で未分類件数を計算中)";
  try {{
    // 未分類件数はこのページ描画時点のものではなく、クリックした瞬間にサーバー側で
    // ログ全体を現在のconfigで再計算した値が使われる(ページの数値が古い場合があるため)。
    const res = await fetch("/actions/launch_claude_config", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: "{{}}",
    }});
    const data = await res.json();
    status.textContent = data.ok
      ? `プロンプトをクリップボードにコピーしました(現在の未分類: ${{data.unclassified_count}}件)。開いたターミナルでclaudeが起動していたら、そのままそこに貼り付けてください` +
        "(claudeが自動起動していなければ、先に「claude」と入力してEnterを押してから貼り付けてください)。"
      : `エラー: ${{data.error}}`;
  }} catch (e) {{
    status.textContent = "エラー: " + e;
  }} finally {{
    setButtonsBusy(false);
  }}
}}
</script>
</body>
</html>
"""
