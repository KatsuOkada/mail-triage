import base64

from mail_triage.mail_body import extract_body_text, html_to_text


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def _payload(plain: str | None = None, html: str | None = None) -> dict:
    parts = []
    if plain is not None:
        parts.append({"mimeType": "text/plain", "body": {"data": _b64(plain)}})
    if html is not None:
        parts.append({"mimeType": "text/html", "body": {"data": _b64(html)}})
    return {"mimeType": "multipart/alternative", "body": {"size": 0}, "parts": parts}


def test_html_to_text_drops_style_and_script():
    html = (
        "<html><head><style>.a{color:red}</style><title>t</title></head>"
        "<body><script>var x = 1;</script><p>荷物は配達済みです</p></body></html>"
    )
    assert html_to_text(html) == "荷物は配達済みです"


def test_html_to_text_keeps_line_breaks_between_blocks():
    html = "<div>配達済み</div><table><tr><td>ロッカー番号：1、</td><td>暗証番号：0000</td></tr></table>"
    assert html_to_text(html) == "配達済み\nロッカー番号：1、 暗証番号：0000"


def test_html_to_text_removes_invisible_chars_and_collapses_spaces():
    # 見えない文字は数値文字参照で書く(U+034F・U+00AD・U+200C・U+202B)
    html = "<p>件名&amp;本文" + "&#847; &#173;&#8204;" * 50 + "</p><p>&#8235;注文番号&nbsp;&nbsp;  X</p>"
    assert html_to_text(html) == "件名&本文\n注文番号 X"


def test_html_to_text_drops_display_none_preheader():
    # 一覧用の一行説明(件名と見えない空白文字の詰め物)は display:none で隠されている
    html = (
        '<body><div style="display:none;font-size:1px;max-height:0px;opacity:0;overflow:hidden;">'
        "配達済み: 「サンプル商品」&#847; &zwnj; &nbsp;<span>入れ子も隠れる</span></div>"
        "<p>荷物は配達済みです!</p></body>"
    )
    assert html_to_text(html) == "荷物は配達済みです!"


def test_html_to_text_hidden_void_element_does_not_hide_following_text():
    html = '<p><img src="x.png" style="display:none">ロゴの後ろの文字</p>'
    assert html_to_text(html) == "ロゴの後ろの文字"


def test_html_to_text_drops_visibility_hidden_and_hidden_attribute():
    html = '<p>見える</p><p style="visibility: hidden">見えない1</p><p hidden>見えない2</p><p>見える2</p>'
    assert html_to_text(html) == "見える\n見える2"


def test_html_to_text_recovers_after_unclosed_tags():
    html = '<div style="display:none"><p>隠れる<span>閉じ忘れ</div><p>表示される</p>'
    assert html_to_text(html) == "表示される"


def test_extract_prefers_html_part():
    # ボックス情報はHTML部分にだけ入っている
    payload = _payload(plain="荷物は配達済みです", html="<p>荷物は配達済みです</p><p>ロッカー番号：1、暗証番号：0000</p>")
    assert "暗証番号：0000" in extract_body_text(payload)


def test_extract_falls_back_to_plain_text():
    payload = _payload(plain="  プレーンテキストだけのメール  ")
    assert extract_body_text(payload) == "プレーンテキストだけのメール"


def test_extract_single_part_message():
    payload = {"mimeType": "text/html", "body": {"data": _b64("<b>一枚だけ</b>")}}
    assert extract_body_text(payload) == "一枚だけ"


def test_extract_nested_multipart():
    inner = _payload(html="<p>入れ子の本文</p>")
    payload = {"mimeType": "multipart/mixed", "body": {"size": 0}, "parts": [inner]}
    assert extract_body_text(payload) == "入れ子の本文"


def test_extract_without_text_parts_returns_empty():
    assert extract_body_text({"mimeType": "multipart/mixed", "body": {"size": 0}, "parts": []}) == ""


def test_extract_truncates_to_max_chars():
    payload = _payload(html="<p>" + "あ" * 100 + "</p>")
    assert extract_body_text(payload, max_chars=10) == "あ" * 10


def test_extract_redacts_matching_text():
    payload = _payload(html="<p>山田太郎 - 東京都</p><p>注文番号 123-4567890-1234567</p>")
    text = extract_body_text(payload, redact_regexes=["山田太郎", r"\d{3}-\d{7}-\d{7}"])
    assert text == "＊ - 東京都\n注文番号 ＊"
