"""Merge subtitles and frame descriptions into one timestamped file."""

from pathlib import Path

from .sheets import stamp

SPEECH_CHUNK = 15  # seconds of subtitles per SPEECH line


def write(meta: dict, cues: list[tuple[float, str]], visuals: list[tuple[int, str, str]],
          frames_dir: Path, out: Path) -> Path:
    entries: list[tuple[int, int, str]] = []  # (seconds, order, line)

    chunk_start, words = None, []
    for t, text in cues + [(float("inf"), "")]:
        if chunk_start is not None and (t - chunk_start >= SPEECH_CHUNK or t == float("inf")):
            entries.append((chunk_start, 0, f"SPEECH  {' '.join(words)}"))
            chunk_start, words = None, []
        if t != float("inf"):
            chunk_start = int(t) if chunk_start is None else chunk_start
            words.append(text)

    seen = set()
    for t, kind, desc in sorted(visuals):
        desc = desc.replace("`", "").strip()
        if not desc or (kind, desc) in seen:  # the same code often shows on many frames
            continue
        seen.add((kind, desc))
        entries.append((t, 1, f"{kind:<7} {desc}"))

    minutes = int(meta["duration"]) // 60
    lines = [
        f"# {meta['title']}",
        "",
        f"- URL: {meta['url']}",
        f"- Length: {minutes} min {int(meta['duration']) % 60} s",
        f"- Frames: {frames_dir} (named by second, e.g. 00252.jpg = 04:12)",
        "",
        "```",
        *(f"[{stamp(t)}] {line}" for t, _, line in sorted(entries)),
        "```",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
