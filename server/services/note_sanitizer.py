"""Allow-list HTML sanitizer for private lesson notes."""

import re
from html import escape
from html.parser import HTMLParser

from fastapi import HTTPException

MAX_NOTE_HTML_BYTES = 250_000


class NoteSanitizer(HTMLParser):
    allowed = {
        "p", "div", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li",
        "blockquote", "pre", "code", "h1", "h2", "h3", "a", "img", "span", "table",
        "thead", "tbody", "tr", "th", "td",
    }
    void = {"br", "img"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.allowed:
            return
        clean = []
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href", "").startswith(("http://", "https://")):
            clean = [("href", attrs["href"]), ("target", "_blank"), ("rel", "noopener noreferrer")]
        elif tag == "img":
            src = attrs.get("src", "")
            if not re.fullmatch(r"/api/notes/images/[a-f0-9-]+\.(?:png|jpe?g|webp|gif)", src):
                return
            width = attrs.get("data-width", "100")
            align = attrs.get("data-align", "left")
            caption = attrs.get("data-caption", "").strip()[:500]
            if width not in {"25", "50", "75", "100"}:
                width = "100"
            if align not in {"left", "center", "right"}:
                align = "left"
            clean = [("src", src), ("data-width", width), ("data-align", align)]
            if caption:
                clean.append(("data-caption", caption))
        elif tag in {"p", "h1", "h2", "h3"}:
            align_match = re.search(r"text-align:\s*(left|center|right|justify)", attrs.get("style", ""))
            indent = attrs.get("data-indent", "0")
            if indent not in {"1", "2", "3", "4", "5", "6"}:
                indent = "0"
            if align_match:
                clean.append(("style", f"text-align:{align_match.group(1)}"))
            if indent != "0":
                clean.append(("data-indent", indent))
        elif tag == "span":
            match = re.search(r"font-size:\s*(12|15|18|24)px", attrs.get("style", ""))
            if match:
                clean = [("style", f"font-size:{match.group(1)}px")]
        self.out.append("<" + tag + "".join(f' {key}="{escape(value, quote=True)}"' for key, value in clean) + ">")

    def handle_endtag(self, tag):
        if tag in self.allowed and tag not in self.void:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(escape(data))


def sanitize_note_html(value: str) -> str:
    if len(value.encode("utf-8")) > MAX_NOTE_HTML_BYTES:
        raise HTTPException(status_code=400, detail="Note is too large")
    parser = NoteSanitizer()
    parser.feed(value)
    parser.close()
    return "".join(parser.out)
