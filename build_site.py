"""Build site/index.html: every change to every tracked page, grouped by day (Brasília time).

Reads snapshots/<page_id>/vNNNN.{html,json} written by fetch.py, converts each version's
Confluence XHTML into readable lines (paragraphs, list items, table rows as `cell │ cell`),
and diffs each version against the previous one with difflib (line level, then word level).

Usage: python3 build_site.py      → writes site/index.html
"""
import difflib
import html
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

from common import ROOT, SITE, SNAPSHOTS, read_page_ids

try:
    from zoneinfo import ZoneInfo
    BRT = ZoneInfo("America/Sao_Paulo")
except Exception:  # no tz database installed; Brasília has had no DST since 2019
    BRT = timezone(timedelta(hours=-3), "BRT")

OUT = ROOT / "site"
CONTEXT = 2  # unchanged lines shown around each change
WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


# ---------------------------------------------------------------- XHTML → lines
class TextExtractor(HTMLParser):
    BLOCKS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "table", "ul", "ol"}
    SKIP = {"ac:parameter", "style", "script"}  # macro settings, not visible content

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.buf = [], []
        self.prefix = ""
        self.rows = []        # stack: [cells, all_cells_are_th] for the table row(s) we're inside
        self.headers = []     # stack: column names of each open table
        self.cell = None      # text parts of the current cell
        self.skip = 0

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        self.buf = []
        if self.cell is not None:
            if text:
                self.cell.append(text)
        elif text:
            self.lines.append(self.prefix + text)
        self.prefix = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "table":
            self._flush()
            self.headers.append([])
        elif tag == "tr":
            self._flush()
            self.rows.append([[], True])
        elif tag in ("td", "th"):
            self._flush()
            self.cell = []
            if tag == "td" and self.rows:
                self.rows[-1][1] = False
        elif tag == "br":
            self._flush()
        elif tag in self.BLOCKS:
            self._flush()
            if tag == "li":
                self.prefix = "• "
            elif re.fullmatch(r"h[1-6]", tag):
                self.prefix = "#" * int(tag[1]) + " "
        elif tag == "ri:attachment":
            self.buf.append(f"[anexo: {a.get('ri:filename', '')}]")
        elif tag == "ri:page" and not self.buf:
            self.buf.append(a.get("ri:content-title", ""))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in self.SKIP:
            self.skip -= 1

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in ("td", "th"):
            self._flush()
            if self.rows and self.cell is not None:
                self.rows[-1][0].append(" · ".join(self.cell))
            self.cell = None
        elif tag == "tr":
            self._flush()
            if self.rows:
                self._emit_row(*self.rows.pop())
        elif tag == "table":
            self._flush()
            if self.headers:
                self.headers.pop()
        elif tag in self.BLOCKS:
            self._flush()

    def _emit_row(self, cells, is_header):
        """Header row → 'Colunas: a │ b'. Data row → '■ key' plus one 'key › Column: value' line per cell,
        so a diff points at the exact cell that changed and says which row it belongs to."""
        if not any(cells):
            return
        headers = self.headers[-1] if self.headers else []
        if is_header and self.headers:
            self.headers[-1] = cells
            self.lines.append("Colunas: " + " │ ".join(cells))
            return
        key = cells[0] or "(linha)"
        self.lines.append(f"■ {key}")
        for i, value in enumerate(cells[1:], start=1):
            if value:
                col = headers[i] if i < len(headers) else f"coluna {i + 1}"
                self.lines.append(f"    {key} › {col}: {value}")

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)

    def unknown_decl(self, data):  # <![CDATA[ … ]]> inside code macros
        if data.startswith("CDATA[") and not self.skip:
            self.buf.append(data[6:])


def to_lines(storage_html):
    p = TextExtractor()
    p.feed(storage_html)
    p.close()
    p._flush()
    return p.lines


# ---------------------------------------------------------------- diff → HTML
TOKEN = re.compile(r"\s+|\w+|[^\w\s]", re.UNICODE)
INVISIBLE = {"​": "ZWSP", "‌": "ZWNJ", "‍": "ZWJ", "⁠": "WJ", "﻿": "BOM", "­": "SHY"}
INVISIBLE_RE = re.compile("[" + "".join(INVISIBLE) + "]")


def esc(s):
    """HTML-escape and make invisible characters visible (e.g. a removed zero-width space)."""
    return INVISIBLE_RE.sub(lambda m: f'<span class="inv" title="caractere invisível">{INVISIBLE[m.group()]}</span>', html.escape(s))


def word_diff(old, new):
    a, b = TOKEN.findall(old), TOKEN.findall(new)
    out_old, out_new = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        x, y = esc("".join(a[i1:i2])), esc("".join(b[j1:j2]))
        if op == "equal":
            out_old.append(x)
            out_new.append(y)
        else:
            if x:
                out_old.append(f"<del>{x}</del>")
            if y:
                out_new.append(f"<ins>{y}</ins>")
    return "".join(out_old), "".join(out_new)


def row(kind, text, is_html=False):
    sign = {"del": "−", "add": "+", "ctx": " "}[kind]
    body = text if is_html else esc(text)
    return f'<tr class="{kind}"><td class="sign">{sign}</td><td class="txt">{body}</td></tr>'


def diff_html(old, new):
    """Return (html, lines_removed, lines_added). Empty html → no textual change."""
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    rows, removed, added = [], 0, 0
    for group in sm.get_grouped_opcodes(CONTEXT):
        if rows:
            rows.append('<tr class="gap"><td></td><td>⋯</td></tr>')
        for op, i1, i2, j1, j2 in group:
            if op == "equal":
                rows += [row("ctx", l) for l in old[i1:i2]]
                continue
            removed += i2 - i1
            added += j2 - j1
            olds, news = old[i1:i2], new[j1:j2]
            if op == "replace":
                # pair up similar lines for word-level highlighting, the rest are plain del/add
                pairs = min(len(olds), len(news))
                dels, adds = [], []
                for k in range(pairs):
                    if difflib.SequenceMatcher(None, olds[k], news[k], autojunk=False).quick_ratio() > 0.4:
                        o, n = word_diff(olds[k], news[k])
                        dels.append(row("del", o, True))
                        adds.append(row("add", n, True))
                    else:
                        dels.append(row("del", olds[k]))
                        adds.append(row("add", news[k]))
                dels += [row("del", l) for l in olds[pairs:]]
                adds += [row("add", l) for l in news[pairs:]]
                rows += dels + adds
            else:
                rows += [row("del", l) for l in olds] + [row("add", l) for l in news]
    if not rows:
        return "", 0, 0
    return f'<table class="diff">{"".join(rows)}</table>', removed, added


# ---------------------------------------------------------------- page assembly
def parse_when(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(BRT)


def load_versions(page_id):
    folder = SNAPSHOTS / page_id
    out = []
    for meta_file in sorted(folder.glob("v*.json")):
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        meta["lines"] = to_lines(meta_file.with_suffix(".html").read_text(encoding="utf-8"))
        out.append(meta)
    return sorted(out, key=lambda m: m["version"])


def page_url(page_id, version=None):
    url = f"{SITE}/wiki/spaces/OF/pages/{page_id}"
    return url + (f"?pageVersion={version}" if version else "")


def build():
    pages, changes = [], []
    for page_id in read_page_ids():
        versions = load_versions(page_id)
        if not versions:
            continue
        latest = versions[-1]
        pages.append(latest)
        for prev, cur in zip([None] + versions[:-1], versions):
            c = dict(cur, when_brt=parse_when(cur["when"]), prev=prev)
            if prev is None:
                c["diff"], c["removed"], c["added"] = "", 0, len(cur["lines"])
            else:
                c["diff"], c["removed"], c["added"] = diff_html(prev["lines"], cur["lines"])
            changes.append(c)

    changes.sort(key=lambda c: (c["when_brt"], c["version"]), reverse=True)
    by_day = defaultdict(list)
    for c in changes:
        by_day[c["when_brt"].date()].append(c)

    color = {p["page_id"]: i % 6 for i, p in enumerate(pages)}
    e = html.escape
    out = []

    # page list / filter
    out.append('<section class="pages"><h2>Páginas monitoradas</h2><ul>')
    for p in pages:
        out.append(
            f'<li><label><input type="checkbox" checked data-page="{p["page_id"]}">'
            f'<span class="dot c{color[p["page_id"]]}"></span>{e(p["title"])}</label> '
            f'<span class="muted">v{p["version"]} · editada {p_when(p)} · '
            f'<a href="{page_url(p["page_id"])}">abrir no Confluence ↗</a></span></li>'
        )
    out.append("</ul></section>")

    first_open = 3
    for day in sorted(by_day, reverse=True):
        label = f'{day.strftime("%d/%m/%Y")} — {WEEKDAYS[day.weekday()]}'
        out.append(f'<section class="day"><h2>{label}</h2>')
        for c in by_day[day]:
            pid = c["page_id"]
            if c["prev"] is None:
                stats = '<span class="tag">página criada</span>'
            elif not c["diff"]:
                stats = '<span class="tag">só formatação</span>'
            else:
                stats = f'<span class="rm">−{c["removed"]}</span> <span class="ad">+{c["added"]}</span>'
            msg = f'<div class="msg">“{e(c["message"])}”</div>' if c["message"] else ""
            vlabel = f'v{c["prev"]["version"]} → v{c["version"]}' if c["prev"] else f'v{c["version"]}'
            body = c["diff"] or (
                f'<p class="muted">Primeira versão ({len(c["lines"])} linhas).</p>' if c["prev"] is None
                else '<p class="muted">O texto não mudou — apenas formatação, estilos ou atributos internos.</p>'
            )
            is_open = " open" if first_open > 0 and c["diff"] else ""
            if is_open:
                first_open -= 1
            out.append(
                f'<details class="change" data-page="{pid}"{is_open}><summary>'
                f'<span class="time">{c["when_brt"].strftime("%H:%M")}</span>'
                f'<span class="dot c{color[pid]}"></span>'
                f'<span class="title">{e(c["title"])}</span>'
                f'<span class="ver">{vlabel}</span>{stats}'
                f'<span class="by">{e(c["author"])}</span>{msg}</summary>'
                f'<div class="body"><p class="links">'
                f'<a href="{page_url(pid, c["version"])}">ver v{c["version"]} no Confluence ↗</a></p>{body}</div></details>'
            )
        out.append("</section>")

    now = datetime.now(BRT).strftime("%d/%m/%Y %H:%M")
    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(TEMPLATE.replace("{{now}}", now).replace("{{content}}", "\n".join(out)), encoding="utf-8")
    (OUT / ".nojekyll").write_text("")
    print(f"wrote {OUT / 'index.html'}: {len(pages)} page(s), {len(changes)} version(s), {len(by_day)} day(s)")


def p_when(p):
    return parse_when(p["when"]).strftime("%d/%m/%Y %H:%M")


TEMPLATE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OFB Docs Tracker</title>
<style>
:root{--bg:#fff;--fg:#1f2328;--muted:#656d76;--line:#d0d7de;--card:#f6f8fa;
--del-bg:#ffebe9;--del-hl:#ff818266;--add-bg:#e6ffec;--add-hl:#4ac26b66;--link:#0969da}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--muted:#8d96a0;--line:#30363d;--card:#161b22;
--del-bg:#3c1618;--del-hl:#f8514966;--add-bg:#12261e;--add-hl:#2ea04366;--link:#4493f8}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
a{color:var(--link)}
h1{font-size:24px;margin:0 0 4px}
h2{font-size:16px;margin:0 0 10px}
.muted{color:var(--muted);font-size:13px}
.pages{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin:16px 0 28px}
.pages ul{list-style:none;margin:0;padding:0}.pages li{margin:6px 0}
.pages label{font-weight:600;cursor:pointer}
.day{margin-top:28px}
.day h2{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);z-index:1}
.change{border:1px solid var(--line);border-radius:8px;margin:10px 0;overflow:hidden}
.change summary{cursor:pointer;padding:10px 14px;background:var(--card);display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center}
.change[open] summary{border-bottom:1px solid var(--line)}
.time{font-variant-numeric:tabular-nums;font-weight:700}
.title{font-weight:600}
.ver,.by{color:var(--muted);font-size:13px}
.msg{flex-basis:100%;font-size:13px;color:var(--muted);font-style:italic}
.rm{color:#cf222e;font-weight:700}.ad{color:#1a7f37;font-weight:700}
@media (prefers-color-scheme:dark){.rm{color:#ff7b72}.ad{color:#3fb950}}
.tag{font-size:12px;border:1px solid var(--line);border-radius:999px;padding:0 8px;color:var(--muted)}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px;flex:none}
.c0{background:#0969da}.c1{background:#bf3989}.c2{background:#bc4c00}.c3{background:#1a7f37}.c4{background:#8250df}.c5{background:#9a6700}
.body{padding:8px 0 0}.links{margin:0 14px 8px;font-size:13px}.body>p.muted{margin:0 14px 12px}
.diff{width:100%;border-collapse:collapse;font:12.5px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace}
.diff td{padding:1px 8px;vertical-align:top;white-space:pre-wrap;word-break:break-word}
.diff .sign{width:1.5em;text-align:center;user-select:none;color:var(--muted)}
.diff tr.del{background:var(--del-bg)}.diff tr.add{background:var(--add-bg)}
.diff tr.ctx .txt{color:var(--muted)}
.diff tr.gap td{text-align:center;color:var(--muted);background:var(--card)}
.diff del{background:var(--del-hl);text-decoration:none;border-radius:2px}
.diff ins{background:var(--add-hl);text-decoration:none;border-radius:2px}
.inv{font-size:9px;border:1px dashed currentColor;border-radius:3px;padding:0 2px;margin:0 1px;vertical-align:1px}
.hidden{display:none}
</style></head><body><main>
<h1>OFB Docs Tracker</h1>
<div class="muted">Mudanças nas páginas do Confluence do Open Finance Brasil, por data de edição (horário de Brasília). Última verificação: {{now}}.</div>
{{content}}
</main>
<script>
document.querySelectorAll('.pages input').forEach(function(cb){cb.addEventListener('change',function(){
  var off=[].slice.call(document.querySelectorAll('.pages input:not(:checked)')).map(function(x){return x.dataset.page});
  document.querySelectorAll('.change').forEach(function(c){c.classList.toggle('hidden',off.indexOf(c.dataset.page)>=0)});
  document.querySelectorAll('.day').forEach(function(d){d.classList.toggle('hidden',!d.querySelector('.change:not(.hidden)'))});
})});
</script>
</body></html>
"""

if __name__ == "__main__":
    build()
