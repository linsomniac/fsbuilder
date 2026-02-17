#!/usr/bin/env python3
"""Generate a self-contained HTML documentation page from ansible-doc JSON output.

AIDEV-NOTE: This script uses only the Python standard library so it can run in CI
without extra dependencies. It reads the JSON output of `ansible-doc --json` and
produces a single-page HTML file with inline CSS.

Usage:
    ansible-doc --json linsomniac.fsbuilder.fsbuilder > doc.json
    python docs/generate_docs.py --input doc.json --output _site/index.html --version 1.0.0
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path


def escape(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text))


def render_options_table(options: dict[str, dict]) -> str:  # type: ignore[type-arg]
    """Render module options as an HTML table."""
    if not options:
        return "<p>No options documented.</p>"

    rows: list[str] = []
    for name in sorted(options):
        opt = options[name]
        required = opt.get("required", False)
        opt_type = opt.get("type", "str")
        default = opt.get("default")
        description_parts = opt.get("description", [])
        if isinstance(description_parts, list):
            description = " ".join(str(d) for d in description_parts)
        else:
            description = str(description_parts)
        choices = opt.get("choices")

        req_badge = '<span class="badge required">required</span>' if required else ""
        default_str = (
            f'<span class="badge default">default: {escape(repr(default))}</span>'
            if default is not None
            else ""
        )
        choices_str = ""
        if choices:
            choices_str = (
                '<span class="badge choices">choices: '
                + ", ".join(escape(str(c)) for c in choices)
                + "</span>"
            )

        # AIDEV-NOTE: Suboptions (nested specs) are rendered as a nested table
        # inside the description cell. Only one level deep is supported.
        suboptions_html = ""
        suboptions = opt.get("suboptions")
        if suboptions:
            suboptions_html = (
                '<div class="suboptions"><strong>Suboptions:</strong>'
                + render_options_table(suboptions)
                + "</div>"
            )

        rows.append(
            f"""<tr>
  <td><code>{escape(name)}</code> {req_badge}</td>
  <td><code>{escape(opt_type)}</code></td>
  <td>{escape(description)} {default_str} {choices_str}{suboptions_html}</td>
</tr>"""
        )

    return f"""<table>
<thead><tr><th>Parameter</th><th>Type</th><th>Description</th></tr></thead>
<tbody>
{"".join(rows)}
</tbody>
</table>"""


def render_return_values(return_docs: dict[str, dict]) -> str:  # type: ignore[type-arg]
    """Render return values as an HTML table."""
    if not return_docs:
        return "<p>No return values documented.</p>"

    rows: list[str] = []
    for name in sorted(return_docs):
        rv = return_docs[name]
        rv_type = rv.get("type", "")
        description_parts = rv.get("description", [])
        if isinstance(description_parts, list):
            description = " ".join(str(d) for d in description_parts)
        else:
            description = str(description_parts)
        returned = rv.get("returned", "")

        rows.append(
            f"""<tr>
  <td><code>{escape(name)}</code></td>
  <td><code>{escape(rv_type)}</code></td>
  <td>{escape(description)}</td>
  <td>{escape(returned)}</td>
</tr>"""
        )

    return f"""<table>
<thead><tr><th>Key</th><th>Type</th><th>Description</th><th>Returned</th></tr></thead>
<tbody>
{"".join(rows)}
</tbody>
</table>"""


def render_examples(examples: str) -> str:
    """Render examples as a code block."""
    if not examples:
        return "<p>No examples documented.</p>"
    return f"<pre><code>{escape(examples.strip())}</code></pre>"


def generate_html(doc_data: dict, version: str) -> str:  # type: ignore[type-arg]
    """Generate a complete self-contained HTML page from ansible-doc JSON."""
    # ansible-doc --json wraps everything in a top-level dict keyed by module FQCN
    if len(doc_data) == 1:
        module_name = next(iter(doc_data))
        module_data = doc_data[module_name]
    else:
        # Fallback: use first key
        module_name = next(iter(doc_data))
        module_data = doc_data[module_name]

    doc = module_data.get("doc", {})
    examples = module_data.get("examples", "")
    return_docs = module_data.get("return", {})

    short_description = doc.get("short_description", "")
    description_parts = doc.get("description", [])
    if isinstance(description_parts, list):
        description = "</p><p>".join(escape(str(d)) for d in description_parts)
    else:
        description = escape(str(description_parts))

    options = doc.get("options", {})

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(module_name)} — Ansible Module Documentation</title>
<style>
:root {{
  --bg: #ffffff;
  --fg: #1a1a1a;
  --muted: #666;
  --border: #ddd;
  --code-bg: #f5f5f5;
  --accent: #0066cc;
  --header-bg: #1a1a2e;
  --header-fg: #e0e0e0;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #1a1a1a;
    --fg: #e0e0e0;
    --muted: #999;
    --border: #444;
    --code-bg: #2a2a2a;
    --accent: #5599dd;
    --header-bg: #0d0d1a;
    --header-fg: #e0e0e0;
  }}
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.6;
  color: var(--fg);
  background: var(--bg);
}}
header {{
  background: var(--header-bg);
  color: var(--header-fg);
  padding: 2rem;
}}
header h1 {{ font-size: 1.8rem; margin-bottom: 0.3rem; }}
header p {{ color: var(--muted); }}
.container {{ max-width: 960px; margin: 0 auto; padding: 2rem 1rem; }}
h2 {{
  font-size: 1.4rem;
  margin: 2rem 0 1rem;
  padding-bottom: 0.3rem;
  border-bottom: 2px solid var(--accent);
}}
table {{
  width: 100%;
  border-collapse: collapse;
  margin: 1rem 0;
  font-size: 0.9rem;
}}
th, td {{
  text-align: left;
  padding: 0.6rem 0.8rem;
  border: 1px solid var(--border);
  vertical-align: top;
}}
th {{ background: var(--code-bg); font-weight: 600; }}
code {{
  background: var(--code-bg);
  padding: 0.15em 0.4em;
  border-radius: 3px;
  font-size: 0.9em;
}}
pre {{
  background: var(--code-bg);
  padding: 1rem;
  overflow-x: auto;
  border-radius: 6px;
  margin: 1rem 0;
}}
pre code {{ background: none; padding: 0; }}
.badge {{
  display: inline-block;
  font-size: 0.75rem;
  padding: 0.1em 0.5em;
  border-radius: 3px;
  margin-left: 0.3em;
  vertical-align: middle;
}}
.badge.required {{ background: #e74c3c; color: #fff; }}
.badge.default {{ background: var(--code-bg); color: var(--muted); }}
.badge.choices {{ background: var(--code-bg); color: var(--muted); }}
.suboptions {{ margin-top: 0.8rem; }}
.suboptions table {{ font-size: 0.85rem; }}
footer {{
  text-align: center;
  padding: 2rem;
  color: var(--muted);
  font-size: 0.85rem;
}}
</style>
</head>
<body>
<header>
  <div class="container">
    <h1>{escape(module_name)}</h1>
    <p>{escape(short_description)}</p>
    <p>Version {escape(version)}</p>
  </div>
</header>
<div class="container">

<h2>Description</h2>
<p>{description}</p>

<h2>Parameters</h2>
{render_options_table(options)}

<h2>Examples</h2>
{render_examples(examples)}

<h2>Return Values</h2>
{render_return_values(return_docs or {})}

</div>
<footer>
  Generated from <code>ansible-doc --json</code> &mdash;
  <a href="https://github.com/linsomniac/fsbuilder">linsomniac/fsbuilder</a>
</footer>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML docs from ansible-doc JSON output")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to ansible-doc JSON file",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the HTML output",
    )
    parser.add_argument(
        "--version",
        default="dev",
        help="Version string to display in the docs",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    doc_data = json.loads(input_path.read_text())
    html_output = generate_html(doc_data, args.version)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_output)
    print(f"Wrote documentation to {output_path}")


if __name__ == "__main__":
    main()
