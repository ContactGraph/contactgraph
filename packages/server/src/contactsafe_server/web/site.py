from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT: Path = Path(__file__).resolve().parents[5]
_MANIFESTO_PATH: Path = _REPO_ROOT / "manifesto.md"

_GITHUB_REPO_URL: str = "https://github.com/ContactGraph/contactgraph"
_SITE_YEAR: str = str(datetime.now(tz=UTC).year)
_SITE_NAME: str = "ContactGraph"
_TAGLINE: str = "Turn your contacts into a superpower."
_LANDING_DESCRIPTION: str = (
    f"{_TAGLINE} Connect Gmail via MCP, sync your network, and query it in "
    "natural language."
)
_MANIFESTO_DESCRIPTION: str = (
    f"{_TAGLINE} We gave away our relationships — ContactGraph builds a private "
    "graph from your email so your agent can answer who you know."
)


@dataclass(frozen=True, slots=True)
class PageMeta:
    title: str
    description: str
    path: str
    og_type: str = "website"

_MONO: str = (
    'ui-monospace, "SFMono-Regular", "Berkeley Mono", Menlo, Consolas, '
    '"Liberation Mono", monospace'
)

_BASE_STYLES: str = f"""
    :root {{
      color-scheme: light;
      --bg: #f7f7f8;
      --ink: #070707;
      --muted: #5a5a5a;
      --line: #070707;
      --mono: {_MONO};
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      padding: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: var(--mono);
      font-size: 12px;
      line-height: 20px;
      -webkit-font-smoothing: antialiased;
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
      text-underline-offset: 2px;
    }}
    .page {{
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    .masthead {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 24px;
      padding: 20px;
      border-bottom: 1px solid var(--line);
    }}
    .brand-block {{
      display: flex;
      flex-direction: column;
      gap: 2px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .brand-block a {{
      display: inline-block;
      font-weight: 700;
    }}
    .brand-block a:hover {{
      text-decoration: none;
      background: var(--ink);
      color: var(--bg);
    }}
    .brand-meta {{
      color: var(--muted);
    }}
    .nav-block {{
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 6px;
      text-align: right;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .nav-bracket {{
      white-space: nowrap;
    }}
    .content {{
      flex: 1;
      padding: 28px 20px 48px;
      max-width: 760px;
    }}
    .content-wide {{
      max-width: 860px;
    }}
    h1 {{
      margin: 0 0 20px;
      font-size: 12px;
      line-height: 20px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      max-width: 42ch;
    }}
    .lead {{
      margin: 0 0 16px;
      max-width: 62ch;
    }}
    .lead:last-of-type {{
      margin-bottom: 0;
    }}
    .status {{
      margin-top: 24px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }}
    .prose {{
      max-width: 62ch;
    }}
    .prose h2 {{
      margin: 28px 0 12px;
      font-size: 12px;
      line-height: 20px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .prose p {{
      margin: 0 0 16px;
    }}
    .prose ol, .prose ul {{
      margin: 0 0 16px;
      padding-left: 20px;
    }}
    .prose li {{
      margin-bottom: 8px;
    }}
    .prose hr {{
      border: none;
      border-top: 1px solid var(--line);
      margin: 28px 0;
    }}
    .prose em {{
      font-style: italic;
    }}
    .prose strong {{
      font-weight: 700;
    }}
    .prose .doc-title {{
      margin: 0 0 24px;
      font-size: 12px;
      line-height: 20px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .site-footer {{
      border-top: 1px solid var(--line);
      padding: 20px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .site-footer .rule {{
      margin: 16px 0;
      color: var(--ink);
      letter-spacing: 0.2em;
    }}
    .site-footer .links {{
      color: var(--ink);
      text-transform: none;
      letter-spacing: 0;
      line-height: 24px;
    }}
    .site-footer .links a {{
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    @media (max-width: 720px) {{
      .masthead {{
        flex-direction: column;
      }}
      .nav-block {{
        align-items: flex-start;
        text-align: left;
      }}
    }}
"""


def _inline_markdown(text: str) -> str:
    escaped: str = html.escape(text, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    return escaped


def _render_manifesto_body(markdown: str, *, page_title: str) -> str:
    blocks: list[str] = [f'<h1 class="doc-title">{html.escape(page_title.upper())}</h1>']
    lines: list[str] = markdown.strip().splitlines()
    index: int = 0

    while index < len(lines):
        line: str = lines[index].strip()

        if not line:
            index += 1
            continue

        if line.startswith("# "):
            index += 1
            continue

        if line.startswith("## "):
            blocks.append(f"<h2>{_inline_markdown(line[3:])}</h2>")
            index += 1
            continue

        if line.startswith("---"):
            blocks.append("<hr />")
            index += 1
            continue

        if re.match(r"^\d+\.\s", line):
            items: list[str] = []
            while index < len(lines):
                item_line: str = lines[index].strip()
                if not item_line:
                    index += 1
                    continue
                if not re.match(r"^\d+\.\s", item_line):
                    break
                item_text: str = re.sub(r"^\d+\.\s", "", item_line)
                items.append(f"<li>{_inline_markdown(item_text)}</li>")
                index += 1
            blocks.append(f"<ol>{''.join(items)}</ol>")
            continue

        if line.startswith("- "):
            items: list[str] = []
            while index < len(lines):
                item_line: str = lines[index].strip()
                if not item_line:
                    index += 1
                    continue
                if not item_line.startswith("- "):
                    break
                items.append(f"<li>{_inline_markdown(item_line[2:])}</li>")
                index += 1
            blocks.append(f"<ul>{''.join(items)}</ul>")
            continue

        paragraph_lines: list[str] = [line]
        index += 1
        while index < len(lines):
            next_line: str = lines[index].strip()
            if (
                not next_line
                or next_line.startswith("#")
                or next_line.startswith("- ")
                or re.match(r"^\d+\.\s", next_line)
                or next_line.startswith("---")
            ):
                break
            paragraph_lines.append(next_line)
            index += 1
        blocks.append(f"<p>{_inline_markdown(' '.join(paragraph_lines))}</p>")

    return "\n        ".join(blocks)


def _nav_html(*, mcp_path: str) -> str:
    mcp_href: str = html.escape(mcp_path)
    return f"""
        <div class="nav-bracket">[
          <a href="/skill.md">SKILL.MD</a>
          /
          <a href="{mcp_href}">MCP</a>
          /
          <a href="{_GITHUB_REPO_URL}">GITHUB</a>
          /
          <a href="/manifesto">MANIFESTO</a>
        ]</div>"""


def _header_html(*, mcp_path: str) -> str:
    nav: str = _nav_html(mcp_path=mcp_path)
    return f"""
    <header>
      <div class="masthead">
        <div class="brand-block">
          <a href="/">CONTACTGRAPH</a>
          <div class="brand-meta">{html.escape(_SITE_YEAR)}</div>
        </div>
        <nav class="nav-block" aria-label="ContactGraph links">
          {nav}
        </nav>
      </div>
    </header>"""


def _footer_html() -> str:
    return f"""
    <footer class="site-footer">
      <div>~*~ © ContactGraph ~*~</div>
      <div class="rule">–––</div>
      <div class="links">
        <a href="/skill.md">Skill</a> |
        <a href="/manifesto">Manifesto</a> |
        <a href="{_GITHUB_REPO_URL}">GitHub</a>
      </div>
    </footer>"""


def _canonical_url(base_url: str, path: str) -> str:
    normalized_base: str = base_url.rstrip("/")
    if path == "/":
        return normalized_base + "/"
    return f"{normalized_base}{path}"


def _head_meta_html(*, meta: PageMeta, base_url: str) -> str:
    canonical_url: str = _canonical_url(base_url, meta.path)
    title: str = html.escape(meta.title)
    description: str = html.escape(meta.description)
    url: str = html.escape(canonical_url, quote=True)
    site_name: str = html.escape(_SITE_NAME)
    og_type: str = html.escape(meta.og_type)
    return f"""
  <meta name="description" content="{description}" />
  <link rel="canonical" href="{url}" />
  <meta property="og:site_name" content="{site_name}" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:url" content="{url}" />
  <meta property="og:type" content="{og_type}" />
  <meta property="og:locale" content="en_US" />
  <meta name="twitter:card" content="summary" />
  <meta name="twitter:title" content="{title}" />
  <meta name="twitter:description" content="{description}" />"""


def _page_shell(*, meta: PageMeta, base_url: str, header: str, content: str) -> str:
    footer: str = _footer_html()
    head_meta: str = _head_meta_html(meta=meta, base_url=base_url)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(meta.title)}</title>{head_meta}
  <style>{_BASE_STYLES}</style>
</head>
<body>
  <div class="page">
    {header}
    {content}
    {footer}
  </div>
</body>
</html>"""


def render_landing_page(*, mcp_path: str, base_url: str) -> str:
    header: str = _header_html(mcp_path=mcp_path)
    content: str = f"""
    <main class="content">
      <h1>{html.escape(_TAGLINE)}</h1>
      <p class="lead">
        ContactGraph distills your inboxes, calendars, and messages into a living relationship graph for AI.
        Ask one question, and the right context appears before the meeting, before the pitch, before the moment is gone.
      </p>
      <p class="lead">
        Connect through MCP. Sync your sources. Query your network in natural language.
      </p>
      <p class="status">Private preview opening soon</p>
    </main>"""
    meta = PageMeta(
        title=f"{_SITE_NAME} — {_TAGLINE}",
        description=_LANDING_DESCRIPTION,
        path="/",
    )
    return _page_shell(meta=meta, base_url=base_url, header=header, content=content)


def render_manifesto_page(*, mcp_path: str, base_url: str) -> str:
    markdown: str = _MANIFESTO_PATH.read_text(encoding="utf-8")
    title_match: re.Match[str] | None = re.search(r"^# (.+)$", markdown, re.MULTILINE)
    page_title: str = title_match.group(1) if title_match else "Manifesto"
    prose_html: str = _render_manifesto_body(markdown, page_title=page_title)

    header: str = _header_html(mcp_path=mcp_path)
    content: str = f"""
    <main class="content content-wide">
      <article class="prose">
        {prose_html}
      </article>
    </main>"""
    meta = PageMeta(
        title=f"{page_title} — {_SITE_NAME}",
        description=_MANIFESTO_DESCRIPTION,
        path="/manifesto",
        og_type="article",
    )
    return _page_shell(meta=meta, base_url=base_url, header=header, content=content)
