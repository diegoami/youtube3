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


def asset(name):
    return (ASSETS / name).read_text(encoding="utf-8")


def page_data(export):
    """The export's data as JSON that is safe inside a <script> element."""
    data = {
        "exported_at": export.get("exported_at"),
        "videos": [{field: video.get(field) for field in FIELDS} for video in export["videos"]],
    }
    # "<" is the only character that can end or confuse a script element;
    # JSON.parse reads < back as "<".
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def page_html(export, title="Liked videos"):
    """The page, with its CSS, script and data inlined."""
    script, style = asset("page.js"), asset("page.css")
    if "</script" in script.lower() or "</style" in style.lower():
        raise ValueError("an asset would end its own element early")
    parts = {"TITLE": html.escape(title), "CSS": style, "JS": script, "DATA": page_data(export)}
    # One pass, so nothing inside the data is ever read as a placeholder.
    return re.sub(r"\{\{(TITLE|CSS|JS|DATA)\}\}", lambda match: parts[match.group(1)], asset("page.html"))


def build_page(export, path, title="Liked videos"):
    """Write the page for an export (a dict, or the path of an export file)."""
    if not isinstance(export, dict):
        export = load_export(export)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(page_html(export, title))
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise
    return path
