"""MCP server: lets a model watch a local video file."""

import json
import re
import subprocess
import sys
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import CACHE, frames, load, run, source
from .sheets import stamp

MAX_ENTRIES = 400
MAX_FRAMES = 6
NEAR = 2  # seconds: reuse an already-kept frame this close to the asked time

server = MCPServer(
    "flipframe",
    instructions=(
        "Watch local video files. Call watch_video with a file path first; it returns a "
        "timestamped timeline of speech and on-screen notes. Then call get_frames with "
        "timestamps to look at the actual picture when the notes are not enough "
        "(exact code, small text, diagrams, faces, what something looks like)."
    ),
)


def _log(msg: str) -> None:
    print(f"[flipframe] {msg}", file=sys.stderr, flush=True)


def _seconds(value: str | int) -> int:
    """Accept 252, "252", "252s", "4:12" or "1:04:12"."""
    text = str(value).strip().lower().rstrip("s").strip("[]")
    if re.fullmatch(r"\d+", text):
        return int(text)
    parts = text.split(":")
    if (not 2 <= len(parts) <= 3 or not all(re.fullmatch(r"\d{1,2}", p) for p in parts)
            or any(int(p) > 59 for p in parts[1:])):
        raise ToolError(f"Can't read the time {value!r}. Use MM:SS, H:MM:SS or seconds.")
    total = 0
    for p in parts:
        total = total * 60 + int(p)
    return total


def _find(video: str) -> dict:
    """Look a video up by its id or by the file path it was processed from."""
    video = video.strip()
    if re.fullmatch(r"[0-9a-f]{12}", video) and (data := load(video)):
        return data
    path = Path(video).expanduser()
    if path.is_file():
        data = load(source.video_key(path.resolve()))
        if data:
            return data
        raise ToolError(f"{path.name} hasn't been watched yet. Call watch_video on it first.")
    raise ToolError(f"No watched video matches {video!r}. Use a file path or an id from list_videos.")


def _render(data: dict, entries: list[dict], note: str = "") -> str:
    head = [
        f"Video: {data['title']}",
        f"Id: {data['id']}",
        f"File: {data['source']}",
        f"Length: {stamp(data['duration'])}",
        f"Frames kept at: {', '.join(stamp(s) for s in data['frames'])}",
        "",
        "Kinds: SPEECH = what was said; SCREEN / TEXT / ACTION = what was shown.",
        "",
    ]
    body = [f"[{stamp(e['t'])}] {e['kind']} {e['text']}" for e in entries] or ["(nothing in this range)"]
    return "\n".join(head + body + ([f"\n{note}"] if note else []))


@server.tool()
def watch_video(path: str, coding: bool = False, force: bool = False) -> str:
    """Watch a local video file and return its timeline.

    The timeline lists what was said (SPEECH, transcribed from the audio) and what was on
    screen (SCREEN, TEXT, ACTION), each with a [MM:SS] timestamp. The first run on a file
    takes a while (roughly 20-60 s for a 10-minute video); later calls are instant.

    Args:
        path: Absolute path to a video file on this machine (mp4, mkv, mov, webm, ...).
        coding: Set true when the video shows code or small text; frames are shown larger
            so symbols are read correctly. Slower.
        force: Reprocess even if this file was watched before.
    """
    try:
        workdir = run(path, grid=2 if coding else 3, force=force, log=_log)
    except FileNotFoundError as e:
        raise ToolError(f"{e}. Pass the absolute path of a video file on this machine.") from e
    except ValueError as e:
        raise ToolError(str(e)) from e
    except subprocess.CalledProcessError as e:
        raise ToolError(f"ffmpeg couldn't read {Path(path).name}. Is it a video file?") from e
    data = json.loads((workdir / "timeline.json").read_text(encoding="utf-8"))
    entries = data["entries"]
    note = "Use get_frames with timestamps to see the picture at any moment."
    if len(entries) > MAX_ENTRIES:
        last = entries[MAX_ENTRIES - 1]["t"]
        entries = entries[:MAX_ENTRIES]
        note = (f"Timeline cut off after {stamp(last)} because it is long. Call get_timeline "
                f"with start='{stamp(last)}' to read on. " + note)
    return _render(data, entries, note)


@server.tool()
def get_timeline(video: str, start: str | None = None, end: str | None = None,
                 kinds: list[str] | None = None) -> str:
    """Read part of a watched video's timeline.

    Args:
        video: The file path or the id returned by watch_video.
        start: Only entries from this time on, e.g. "10:00".
        end: Only entries up to this time, e.g. "20:00".
        kinds: Only these kinds, from SPEECH, SCREEN, TEXT, ACTION.
    """
    data = _find(video)
    lo = _seconds(start) if start else 0
    hi = _seconds(end) if end else data["duration"]
    wanted = {k.upper() for k in kinds} if kinds else None
    entries = [e for e in data["entries"]
               if lo <= e["t"] <= hi and (wanted is None or e["kind"] in wanted)]
    note = ""
    if len(entries) > MAX_ENTRIES:
        last = entries[MAX_ENTRIES - 1]["t"]
        entries = entries[:MAX_ENTRIES]
        note = f"Cut off after {stamp(last)}. Call again with start='{stamp(last)}'."
    return _render(data, entries, note)


@server.tool()
def get_frames(video: str, timestamps: list[str]) -> list:
    """Look at the actual video picture at specific moments.

    Returns one image per timestamp (up to 6 per call). Use it to read exact code or text,
    check a diagram, or see anything the timeline notes don't capture.

    Args:
        video: The file path or the id returned by watch_video.
        timestamps: Moments to look at, e.g. ["4:12", "07:30"] or seconds like ["252"].
    """
    data = _find(video)
    workdir = CACHE / data["id"]
    src = Path(data["source"])
    out: list = []
    for raw in timestamps[:MAX_FRAMES]:
        t = min(max(_seconds(raw), 0), max(data["duration"] - 1, 0))
        kept = min(data["frames"], key=lambda f: abs(f - t)) if data["frames"] else None
        if kept is not None and abs(kept - t) <= NEAR:
            path, shown = workdir / "frames" / f"{kept:05d}.jpg", kept
        elif src.is_file():
            got = frames.extract(src, [t], workdir / "closeups")
            path, shown = (got[0], t) if got else (None, t)
        elif kept is not None:
            path, shown = workdir / "frames" / f"{kept:05d}.jpg", kept
        else:
            path, shown = None, t
        if path and path.exists():
            out.append(f"Frame at [{stamp(shown)}]" + ("" if shown == t else f" (closest to {stamp(t)}; original file is gone)"))
            out.append(Image(path=path))
        else:
            out.append(f"No frame available at [{stamp(t)}].")
    if len(timestamps) > MAX_FRAMES:
        out.append(f"Only the first {MAX_FRAMES} timestamps were shown. Ask again for the rest.")
    return out


@server.tool()
def list_videos() -> str:
    """List videos that have already been watched, newest first."""
    found = []
    for path in CACHE.glob("*/timeline.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "source" in data:
            found.append((path.stat().st_mtime, data))
    if not found:
        return "No videos watched yet. Call watch_video with a file path."
    return "\n".join(f"{d['id']}  {stamp(d['duration'])}  {d['title']}  ({d['source']})"
                     for _, d in sorted(found, key=lambda x: -x[0]))
