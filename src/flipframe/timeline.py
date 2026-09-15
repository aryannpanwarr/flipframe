"""Merge subtitles and frame descriptions into one timestamped timeline."""

import json
from pathlib import Path

from .sheets import stamp

SPEECH_CHUNK = 15  # seconds of subtitles per SPEECH entry


def entries(cues: list[tuple[float, str]], visuals: list[tuple[int, str, str]]) -> list[dict]:
    out: list[tuple[int, int, str, str]] = []  # (seconds, order, kind, text)

    chunk_start, words = None, []
    for t, text in cues:
        if chunk_start is not None and t - chunk_start >= SPEECH_CHUNK:
            out.append((chunk_start, 0, "SPEECH", " ".join(words)))
            chunk_start, words = None, []
        chunk_start = int(t) if chunk_start is None else chunk_start
        words.append(text)
    if words:
        out.append((chunk_start, 0, "SPEECH", " ".join(words)))

    seen = set()
    for t, kind, desc in sorted(visuals):
        desc = desc.replace("`", "").strip()
        if not desc or (kind, desc) in seen:  # the same code often shows on many frames
            continue
        seen.add((kind, desc))
        out.append((t, 1, kind, desc))

    return [{"t": t, "kind": kind, "text": text} for t, _, kind, text in sorted(out)]


def write(meta: dict, items: list[dict], frame_seconds: list[int], workdir: Path) -> Path:
    """Write timeline.json (for the web page) and timeline.md (for reading)."""
    duration = int(meta["duration"])
    data = {
        "id": meta["id"], "title": meta["title"], "source": meta["source"],
        "duration": duration, "frames": frame_seconds, "entries": items,
    }
    (workdir / "timeline.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [
        f"# {meta['title']}",
        "",
        f"- File: {meta['source']}",
        f"- Length: {duration // 60} min {duration % 60} s",
        f"- Frames: {workdir / 'frames'} (named by second, e.g. 00252.jpg = 04:12)",
        "",
        "```",
        *(f"[{stamp(e['t'])}] {e['kind']:<7} {e['text']}" for e in items),
        "```",
        "",
    ]
    out = workdir / "timeline.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
