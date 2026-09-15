"""Step 1 + 2: download a small copy of the video and its subtitles."""

import re
from pathlib import Path

from yt_dlp import YoutubeDL


def fetch(url: str, workdir: Path) -> dict:
    """Download 360p video (no audio) and English subtitles into workdir."""
    opts = {
        "format": "bv*[height<=360][ext=mp4]/bv*[height<=360]/wv*/w",
        "outtmpl": str(workdir / "video.%(ext)s"),
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-orig"],
        "subtitlesformat": "vtt",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    video = next(p for p in workdir.glob("video.*") if p.suffix != ".vtt")
    subs = sorted(workdir.glob("video*.vtt"))
    return {
        "id": info["id"],
        "title": info.get("title", ""),
        "duration": info.get("duration") or 0,
        "url": info.get("webpage_url", url),
        "video": video,
        "subs": subs[0] if subs else None,
    }


def video_id(url: str) -> str | None:
    """Pull the 11-char YouTube id out of a URL without a network call."""
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([\w-]{11})", url)
    return m.group(1) if m else None


_TIME = re.compile(r"(\d+):(\d\d):(\d\d)\.(\d+)\s+-->")
_TAG = re.compile(r"<[^>]+>")


def parse_vtt(path: Path) -> list[tuple[float, str]]:
    """Return (start_seconds, text) cues.

    YouTube auto-captions repeat each line as it scrolls, so a line is kept
    only the first time it appears.
    """
    cues, seen_last, start = [], None, 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _TIME.match(line)
        if m:
            h, mi, s, _ = m.groups()
            start = int(h) * 3600 + int(mi) * 60 + int(s)
            continue
        text = _TAG.sub("", line).strip()
        if not text or text == "WEBVTT" or text.startswith(("Kind:", "Language:")):
            continue
        if text != seen_last:
            cues.append((start, text))
            seen_last = text
    return cues
