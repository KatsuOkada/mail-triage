from __future__ import annotations

import base64
import re
from html.parser import HTMLParser
from typing import Any

# Amazonの配達完了通知では、ロッカー番号・暗証番号は本文の先頭近く(注文番号・「配送状況を確認」のすぐ後)にあるため、
# 先頭の数百字で足りる。送る個人情報と処理時間を抑えるため短めにしてある(設定jev_body.max_charsで変えられる)。
DEFAULT_MAX_CHARS = 500


def _char_class(*ranges: tuple[int, int]) -> str:
    return "".join(re.escape(chr(lo)) + ("-" + re.escape(chr(hi)) if hi != lo else "") for lo, hi in ranges)


# メールの一覧用の一行説明を埋めるための見えない文字(ソフトハイフン・結合用・ゼロ幅・書字方向の制御・BOM)
_INVISIBLE = re.compile(
    "[" + _char_class((0xAD, 0xAD), (0x34F, 0x34F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x2064), (0xFEFF, 0xFEFF)) + "]"
)
# 空白(スペース・タブ・ノーブレークスペース・各種幅のスペース・全角スペース)
_SPACES = re.compile("[" + _char_class((0x20, 0x20), (0x09, 0x09), (0xA0, 0xA0), (0x2000, 0x200A), (0x3000, 0x3000)) + "]+")

# 中身が画面に出ないタグ
_SKIP_TAGS = {"style", "script", "head", "title", "template"}
_BLOCK_TAGS = {"br", "p", "div", "tr", "li", "table", "h1", "h2", "h3", "h4", "h5", "h6"}
# 終了タグを持たない要素(これらに display:none があっても、後ろの文字は隠れない)
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)


def _is_hidden(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
    if tag in _SKIP_TAGS:
        return True
    attr_map = dict(attrs)
    return "hidden" in attr_map or bool(_HIDDEN_STYLE.search(attr_map.get("style") or ""))


class _TextExtractor(HTMLParser):
    """画面に表示される文字だけを集める。開いている要素を積んでおき、
    画面に出ない要素(style・script・display:noneなど)の中にいる間は文字を捨てる。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._stack: list[tuple[str, bool]] = []  # (タグ名, その要素の中が隠れているか)

    def _hidden(self) -> bool:
        return bool(self._stack) and self._stack[-1][1]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS and not self._hidden():
            self.parts.append("\n")
        if tag not in _VOID_TAGS:
            self._stack.append((tag, self._hidden() or _is_hidden(tag, attrs)))

    def handle_endtag(self, tag: str) -> None:
        # 閉じ忘れのあるHTMLでも崩れないよう、対応する開始タグまでまとめて閉じる
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break
        if self._hidden():
            return
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._hidden():
            self.parts.append(data)


def _normalize(text: str) -> str:
    """見えない文字を消し、連続する空白を1つにまとめ、空行を詰める。"""
    text = _INVISIBLE.sub("", text)
    lines = (_SPACES.sub(" ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> str:
    """HTMLから画面に表示される文字だけを取り出す(style・script・head・display:noneの要素などは除く)。"""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return _normalize("".join(parser.parts))


def _decode(part: dict[str, Any]) -> str:
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    return raw.decode("utf-8", errors="replace")


def _find_part(payload: dict[str, Any], mime_type: str) -> dict[str, Any] | None:
    if payload.get("mimeType") == mime_type and payload.get("body", {}).get("data"):
        return payload
    for child in payload.get("parts", []) or []:
        found = _find_part(child, mime_type)
        if found is not None:
            return found
    return None


def extract_body_text(
    payload: dict[str, Any],
    max_chars: int = DEFAULT_MAX_CHARS,
    redact_regexes: list[str] | None = None,
) -> str:
    """Gmail API(format=full)のpayloadから本文を文字にして返す(HTMLのソースは返さない)。
    宅配ボックスの番号などHTML部分にしか無い情報があるため、HTML部分があればそちらを優先し、
    無ければtext/plain部分を使う。
    redact_regexesに一致した部分(氏名・注文番号など判定に要らない個人情報)は「＊」に置き換え、
    先頭のmax_chars文字だけを返す。
    """
    html_part = _find_part(payload, "text/html")
    if html_part is not None:
        text = html_to_text(_decode(html_part))
    else:
        plain_part = _find_part(payload, "text/plain")
        text = _normalize(_decode(plain_part)) if plain_part is not None else ""
    for pattern in redact_regexes or []:
        text = re.sub(pattern, "＊", text)
    return text[:max_chars]
