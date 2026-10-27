"""Checkpoint playlist results and retry a fixed failed selection."""

from dataclasses import asdict, dataclass, replace
import json
import os
from pathlib import Path
import tempfile

from . import download


@dataclass(frozen=True)
class BatchEntry:
    position: int
    video_id: str | None
    title: str
    status: str
    reason: str | None = None


@dataclass(frozen=True)
class BatchResult:
    entries: tuple[BatchEntry, ...]

    @property
    def failed(self):
        return sum(entry.status == "failed" for entry in self.entries)

    def summary(self):
        return "; ".join(f"{sum(entry.status == status for entry in self.entries)} {status}"
                         for status in ("downloaded", "failed", "skipped", "not_attempted"))


def _payload(plan, quality, entries):
    return {
        "schema_version": 4,
        "requires_cookies": plan.requires_cookies or plan.access.enabled,
        "playlist_url": plan.url,
        "playlist_title": plan.title,
        "output": str(plan.output.resolve()),
        "archive": str(plan.archive.resolve()),
        "quality": quality,
        "media": asdict(plan.media),
        "transfer": asdict(plan.transfer),
        "entries": [asdict(entry) for entry in entries],
    }


def _checkpoint(path, payload, *, create=False):
    """Create exclusively, then replace snapshots atomically on the same filesystem."""
    temporary = None
    try:
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as stream:
                stream.write(content)
        else:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".youtube3-report-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            os.replace(temporary, path)
    except (OSError, UnicodeError) as error:
        raise download.DownloadError(f"Cannot write download report {path}: {error}") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def download_batch(plan, *, quality=None, continue_on_error=False, report=None):
    """Run a fixed selection, returning results; individual failures are in the result.

    Saving a report requires a new path. Checkpoints keep unvisited entries distinct
    from failures, including when a process is interrupted. Raw backend errors
    are printed locally and are deliberately excluded from report files.
    """
    download._options(plan.output, quality, plan.archive, plan.media, plan.transfer)
    download._check_cookie_paths(plan.access, plan.output, plan.archive, report)
    archived = download._archived_ids(plan.archive)
    entries = [BatchEntry(entry.position, entry.video_id, entry.title,
                          "skipped" if entry.skip_reason or entry.video_id in archived else "not_attempted",
                          entry.skip_reason or ("archived" if entry.video_id in archived else None))
               for entry in plan.entries]
    if any(entry.status == "not_attempted" for entry in entries):
        if plan.requires_cookies and not plan.access.enabled:
            raise download.DownloadError("Re-supply a cookie option to apply this report; cookie access is not saved")
        download._require_audio_tools(plan.media)
        download._backend()
    report_path = Path(report).expanduser() if report is not None else None
    if report_path is not None:
        if report_path.resolve() in {plan.output.resolve(), plan.archive.resolve()}:
            raise download.DownloadError("Report must differ from the output directory and download archive")
        _checkpoint(report_path, _payload(plan, quality, entries), create=True)
    attempted = False
    for index, entry in enumerate(entries):
        blocked = False
        if entry.status != "not_attempted":
            continue
        # Refresh for a reused plan or another entry that completed this same ID.
        if entry.video_id in download._archived_ids(plan.archive):
            entries[index] = replace(entry, status="skipped", reason="archived")
        else:
            if attempted and plan.transfer.sleep_interval:
                download.time.sleep(plan.transfer.sleep_interval)
            attempted = True
            selection = replace(plan, entries=(plan.entries[index],))
            try:
                download.download_playlist(selection, quality=quality)
            except download.DownloadError as error:
                blocked = isinstance(error, download.DownloadBlockedError)
                entries[index] = replace(entry, status="failed", reason="blocked" if blocked else "download_failed")
                print(f"Failed at playlist position {entry.position} ({entry.video_id}): {error}")
            else:
                entries[index] = replace(entry, status="downloaded")
        if report_path is not None:
            _checkpoint(report_path, _payload(plan, quality, entries))
        if blocked or (entries[index].status == "failed" and not continue_on_error):
            break
    return BatchResult(tuple(entries))


def retry_plan(report):
    """Load only failed entries from a versioned report; no network or file writes."""
    try:
        payload = json.loads(Path(report).expanduser().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise download.DownloadError(f"Cannot read download report: {error}") from None
    try:
        version = payload["schema_version"]
        if type(version) is not int or version not in {1, 2, 3, 4}:
            raise ValueError("Unsupported report version")
        if version == 1 and "transfer" in payload:
            raise ValueError("Transfer settings require report version 2")
        if version < 4 and "requires_cookies" in payload:
            raise ValueError("Cookie requirement flag needs report version 4")
        transfer = download.TransferOptions(**payload["transfer"]) if version >= 2 else download.TransferOptions()
        if version < 4 and transfer.sleep_interval is not None:
            raise ValueError("Pacing settings require report version 4")
        requires_cookies = payload["requires_cookies"] if version >= 4 else False
        if type(requires_cookies) is not bool:
            raise ValueError("Invalid cookie requirement flag")
        url = payload["playlist_url"]
        if not isinstance(url, str) or download.playlist_url(url) != url:
            raise ValueError("Invalid playlist URL")
        title = payload["playlist_title"]
        if not isinstance(title, str):
            raise ValueError("Invalid playlist title")
        paths = [payload["output"], payload["archive"]]
        if any(not isinstance(path, str) or not Path(path).is_absolute() for path in paths):
            raise ValueError("Report paths must be absolute paths on this system")
        media_data = payload["media"]
        if version < 3 and media_data.get("format_id") is not None:
            raise ValueError("Exact format selection requires report version 3")
        if any(type(media_data[key]) is not bool
               for key in ("audio_only", "auto_subtitles", "write_metadata", "write_thumbnail")):
            raise ValueError("Invalid media flags")
        if not isinstance(media_data["subtitles"], list):
            raise ValueError("Invalid subtitle languages")
        media = download.MediaOptions(**media_data)
        output, archive = map(Path, paths)
        quality = payload["quality"]
        download._options(output, quality, archive, media, transfer)
        if not isinstance(payload["entries"], list):
            raise ValueError("Invalid report entries")
        entries = []
        positions = set()
        for item in payload["entries"]:
            if (type(item["position"]) is not int or item["position"] < 1
                    or item["position"] in positions or not isinstance(item["title"], str)
                    or item["status"] not in {"downloaded", "failed", "skipped", "not_attempted"}):
                raise ValueError("Invalid report entry")
            positions.add(item["position"])
            if item["status"] == "failed":
                video_id = item["video_id"]
                if not isinstance(video_id, str) or download.video_url(video_id).split("v=")[-1] != video_id:
                    raise ValueError("Invalid failed video ID")
                entries.append(download.PlaylistEntry(item["position"], video_id, item["title"]))
        return download.PlaylistPlan(url, title, output, archive, tuple(entries), media, transfer,
                                     requires_cookies=requires_cookies), quality
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise download.DownloadError(f"Invalid download report: {error}") from None
