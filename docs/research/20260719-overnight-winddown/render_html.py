#!/usr/bin/env python3
"""Render overnight_research wind-down report.md to a self-contained report.html.

Uses Python's stdlib only — no extra deps. The HTML is intentionally minimal:
a single styled page with embedded CSS so the file is portable (can be opened
locally with no server / no CDN).
"""
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

CSS = """
:root { color-scheme: light dark; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    line-height: 1.6;
    max-width: 980px;
    margin: 32px auto;
    padding: 0 24px;
    color: #1f2328;
    background: #fafbfc;
}
@media (prefers-color-scheme: dark) {
    body { color: #e6edf3; background: #0d1117; }
    a { color: #58a6ff; }
    code { background: #161b22; }
    table { background: #0d1117; }
    th, td { border-color: #30363d; }
}
h1, h2, h3, h4 { line-height: 1.25; margin-top: 1.6em; }
h1 { font-size: 1.9rem; border-bottom: 1px solid #d0d7de; padding-bottom: 8px; }
h2 { font-size: 1.45rem; border-bottom: 1px solid #d0d7de; padding-bottom: 6px; }
h3 { font-size: 1.2rem; }
table { border-collapse: collapse; width: 100%; margin: 16px 0; }
th, td { border: 1px solid #d0d7de; padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: #f6f8fa; }
@media (prefers-color-scheme: dark) { th { background: #161b22; } }
ul, ol { padding-left: 1.6em; }
li { margin: 4px 0; }
code { background: #f6f8fa; padding: 1px 4px; border-radius: 3px; font-size: 0.9em; }
blockquote {
    border-left: 3px solid #d0d7de;
    margin: 12px 0;
    padding: 0 12px;
    color: #57606a;
}
hr { border: 0; border-top: 1px solid #d0d7de; margin: 24px 0; }
"""


def md_to_html(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    in_list = False
    in_table = False
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        out.append("<table>")
        header = table_rows[0]
        out.append(
            "<thead><tr>"
            + "".join(f"<th>{html.escape(c)}</th>" for c in header)
            + "</tr></thead>"
        )
        out.append("<tbody>")
        for row in table_rows[2:]:  # skip separator row (---|---)
            out.append(
                "<tr>"
                + "".join(f"<td>{html.escape(c)}</td>" for c in row)
                + "</tr>"
            )
        out.append("</tbody></table>")
        table_rows = []

    def flush_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    def inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(
            r"\*\*(.+?)\*\*",
            r"<strong>\1</strong>",
            s,
        )
        s = re.sub(
            r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)",
            r"<em>\1</em>",
            s,
        )
        s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        s = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', s)
        return s

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush_list()
            if in_table:
                flush_table()
                in_table = False
            out.append("")
            continue

        if line.startswith("### "):
            flush_list()
            flush_table()
            in_table = False
            out.append(f"<h3>{inline(line[4:])}</h3>")
            continue
        if line.startswith("## "):
            flush_list()
            flush_table()
            in_table = False
            out.append(f"<h2>{inline(line[3:])}</h2>")
            continue
        if line.startswith("# "):
            flush_list()
            flush_table()
            in_table = False
            out.append(f"<h1>{inline(line[2:])}</h1>")
            continue

        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            table_rows.append(cells)
            in_table = True
            continue
        if in_table and not line.startswith("|"):
            flush_table()
            in_table = False

        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m:
            flush_list()
            out.append(f"<li>{inline(m.group(2))}</li>")
            in_list = True
            continue
        m = re.match(r"^[-*]\s+(.*)$", line)
        if m:
            flush_list()
            out.append(f"<li>{inline(m.group(1))}</li>")
            in_list = True
            continue

        flush_list()
        out.append(f"<p>{inline(line)}</p>")

    flush_list()
    flush_table()

    body = "\n".join(out)
    return f"<!doctype html><meta charset='utf-8'><title>Overnight Research 终稿</title><style>{CSS}</style><body>{body}</body>"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--md", required=True, type=Path)
    parser.add_argument("--html", required=True, type=Path)
    args = parser.parse_args()
    md = args.md.read_text(encoding="utf-8")
    args.html.write_text(md_to_html(md), encoding="utf-8")
    print(f"wrote {args.html} ({args.html.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())