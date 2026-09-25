"""A self-contained HTML page of the liked videos, from an export (youtube3.likes)."""

import html
import json
import os
import re
import tempfile
from importlib.resources import files
from pathlib import Path

from .likes import load_export

ASSETS = files("youtube3") / "page_assets"
# What the page needs from each record; item_id and the rest stay out of it.
FIELDS = ("video_id", "title", "channel_id", "channel_title", "liked_at", "published_at", "thumbnail", "available")

# A link to another page may only name a sibling file.
SIBLING = re.compile(r"^[\w.-]+\.html$")


def asset(name):
    return (ASSETS / name).read_text(encoding="utf-8")


def _script_json(data):
    """JSON that is safe inside a <script> element."""
    # "<" is the only character that can end or confuse a script element;
    # JSON.parse reads \u003c back as "<".
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def _links(links):
    links = [list(pair) for pair in links]
    for _, href in links:
        if not SIBLING.match(href):
            raise ValueError(f"{href!r}: a page may only link to a sibling .html file")
    return links


def page_data(export, links=()):
    """The export's data as JSON that is safe inside a <script> element."""
    return _script_json(
        {
            "exported_at": export.get("exported_at"),
            "videos": [{field: video.get(field) for field in FIELDS} for video in export["videos"]],
            "links": _links(links),
        }
    )


def _fill(template, title, scripts, data):
    script, style = "\n".join(asset(name) for name in scripts), asset("page.css")
    if "</script" in script.lower() or "</style" in style.lower():
        raise ValueError("an asset would end its own element early")
    parts = {"TITLE": html.escape(title), "CSS": style, "JS": script, "DATA": data}
    # One pass, so nothing inside the data is ever read as a placeholder.
    return re.sub(r"\{\{(TITLE|CSS|JS|DATA)\}\}", lambda match: parts[match.group(1)], asset(template))


def page_html(export, title="Liked videos", links=()):
    """The likes page, with its CSS, script and data inlined."""
    return _fill("page.html", title, ["page.js"], page_data(export, links))


def _write_atomically(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(text)
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise
    return path


def _load(export):
    return export if isinstance(export, dict) else load_export(export)


def build_page(export, path, title="Liked videos", links=()):
    """Write the likes page for an export (a dict, or the path of an export file)."""
    return _write_atomically(path, page_html(_load(export), title, links))

