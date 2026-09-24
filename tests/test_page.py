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


# The history page


def history(*videos):
    return {
        "imported_at": "2026-09-24T12:00:00+00:00",
        "summary": {"first": "2026-01-01T00:00:00Z", "last": "2026-09-20T00:00:00Z", "count": len(videos)},
        "videos": list(videos),
    }


def watched(video_id, **fields):
    record = {
        "video_id": video_id,
        "title": f"title {video_id}",
        "channel_id": "UC1",
        "channel_title": "Channel One",
        "watched_at": "2026-09-20T10:00:00Z",
        "removed": False,
        "ad": False,
        "music": False,
    }
    record.update(fields)
    return record


def history_data(html):
    [data] = re.findall(r'<script id="history-data" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(data)


def test_the_history_page_embeds_what_it_shows_and_the_liked_ids():
    html = page.history_html(history(watched("a"), watched("b")), liked=export(video("b"), video("z")))

    data = history_data(html)
    assert [v["video_id"] for v in data["videos"]] == ["a", "b"]
    assert set(data["videos"][0]) == set(page.HISTORY_FIELDS)
    assert data["liked"] == ["b", "z"]
    assert data["summary"] == {"first": "2026-01-01T00:00:00Z", "last": "2026-09-20T00:00:00Z"}
    assert "function initHistory" in html and "function selectVideos" in html


def test_a_hostile_history_title_stays_data():
    html = page.history_html(history(watched("a", title=HOSTILE, channel_title=HOSTILE)))

    assert html.count("</script>") == 2
    assert "<img src=x" not in html
    assert history_data(html)["videos"][0]["title"] == HOSTILE


def test_the_history_page_is_self_contained():
    html = page.history_html(history(watched("a")))

    assert not re.search(r"<script[^>]*\bsrc=", html)
    assert not re.search(r"<link[^>]*stylesheet", html)
    assert "{{" not in html


@pytest.mark.parametrize("href", ["https://example.com/x.html", "../liked.html", "javascript:alert(1)", "liked.json"])
def test_a_page_links_only_to_a_sibling_html_file(href):
    with pytest.raises(ValueError):
        page.history_html(history(watched("a")), links=[("x", href)])
    with pytest.raises(ValueError):
        page.page_html(export(video("a")), links=[("x", href)])


def test_the_pages_link_to_each_other():
    assert history_data(page.history_html(history(watched("a")), links=[("Liked videos", "liked.html")]))["links"] == [
        ["Liked videos", "liked.html"]
    ]
    assert embedded_data(page.page_html(export(video("a")), links=[("Watch history", "history.html")]))["links"] == [
        ["Watch history", "history.html"]
    ]


def test_build_history_page_from_files(tmp_path):
    source, likes = tmp_path / "history.json", tmp_path / "liked.json"
    source.write_text(json.dumps(history(watched("a"))), encoding="utf-8")
    likes.write_text(json.dumps(export(video("a"))), encoding="utf-8")

    path = page.build_history_page(source, tmp_path / "history.html", liked=likes)

    assert history_data(path.read_text(encoding="utf-8"))["liked"] == ["a"]
