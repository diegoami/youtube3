import json
import re

import pytest

from youtube3 import page

HOSTILE = '</script><img src=x onerror="alert(1)"><!--'


def video(video_id, **fields):
    record = {
        "video_id": video_id,
        "item_id": f"item-{video_id}",
        "title": f"title {video_id}",
        "channel_id": "UC1",
        "channel_title": "Channel One",
        "liked_at": "2026-09-01T10:00:00Z",
        "published_at": "2020-01-01T00:00:00Z",
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "available": True,
    }
    record.update(fields)
    return record


def export(*videos):
    return {"exported_at": "2026-09-24T12:00:00+00:00", "count": len(videos), "videos": list(videos)}


def embedded_data(html):
    [data] = re.findall(r'<script id="likes-data" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(data)


def test_the_page_embeds_what_it_shows_and_nothing_else():
    html = page.page_html(export(video("a"), video("gone", available=False)))

    data = embedded_data(html)
    assert data["exported_at"] == "2026-09-24T12:00:00+00:00"
    assert [v["video_id"] for v in data["videos"]] == ["a", "gone"]
    assert set(data["videos"][0]) == set(page.FIELDS)
    assert "item-a" not in html


def test_a_hostile_title_stays_data():
    html = page.page_html(export(video("a", title=HOSTILE, channel_title=HOSTILE)))

    # Only the data element and the page's own script close a script element.
    assert html.count("</script>") == 2
    assert "<img src=x" not in html
    assert "<!--" not in html
    assert embedded_data(html)["videos"][0]["title"] == HOSTILE


def test_a_placeholder_inside_the_data_is_not_filled():
    html = page.page_html(export(video("a", title="{{JS}} and {{DATA}}")))

    assert embedded_data(html)["videos"][0]["title"] == "{{JS}} and {{DATA}}"


def test_the_page_title_is_escaped():
    html = page.page_html(export(video("a")), title="Mine & <yours>")

    assert "<title>Mine &amp; &lt;yours&gt;</title>" in html


def test_the_page_is_self_contained():
    html = page.page_html(export(video("a")))

    assert not re.search(r"<script[^>]*\bsrc=", html)
    assert not re.search(r"<link[^>]*stylesheet", html)
    assert "{{" not in html.replace("{{JS}} and {{DATA}}", "")
    assert "function selectVideos" in html
    assert "--accent" in html


def test_the_page_keeps_titles_in_their_own_script():
    html = page.page_html(export(video("a", title="Анна Плетнёва - Зима")))

    assert "Анна Плетнёва - Зима" in html


def test_build_page_from_an_export_file(tmp_path):
    source = tmp_path / "liked.json"
    source.write_text(json.dumps(export(video("a"))), encoding="utf-8")

    path = page.build_page(source, tmp_path / "out" / "liked.html")

    assert path == tmp_path / "out" / "liked.html"
    assert embedded_data(path.read_text(encoding="utf-8"))["videos"][0]["video_id"] == "a"
    assert [p.name for p in path.parent.iterdir()] == ["liked.html"]


def test_a_failed_build_leaves_the_previous_page(tmp_path, monkeypatch):
    path = tmp_path / "liked.html"
    path.write_text("the previous page", encoding="utf-8")
    monkeypatch.setattr(page, "page_html", lambda *args: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError):
        page.build_page(export(video("a")), path)

    assert path.read_text(encoding="utf-8") == "the previous page"
    assert [p.name for p in tmp_path.iterdir()] == ["liked.html"]


def test_an_asset_that_would_close_its_element_is_refused(monkeypatch):
    real = page.asset
    monkeypatch.setattr(page, "asset", lambda name: "x</script>y" if name == "page.js" else real(name))

    with pytest.raises(ValueError):
        page.page_html(export(video("a")))


def test_a_placeholder_in_the_page_title_is_not_filled():
    html = page.page_html(export(video("a")), title="{{JS}} {{DATA}}")

    assert "<title>{{JS}} {{DATA}}</title>" in html
