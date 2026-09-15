"""FlipFrame: turn a video file into frames and a timestamped text timeline."""

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from . import describe, frames, sheets, source, timeline, transcribe

PROJECT = Path(__file__).resolve().parents[2]
KEYS = {"claude": ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"],
        "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"]}
CACHE = Path(os.environ.get("FLIPFRAME_CACHE", Path.home() / ".cache" / "flipframe"))


def load_env() -> None:
    """Load .env from the working directory, or from the project when launched elsewhere (MCP)."""
    load_dotenv(find_dotenv(usecwd=True))
    load_dotenv(PROJECT / ".env")


def has_key(provider: str = "gemini") -> bool:
    return any(os.environ.get(k) for k in KEYS[provider])


def load(video_id: str) -> dict | None:
    path = CACHE / video_id / "timeline.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def run(path: str | Path, *, budget: int = 90, threshold: float = 0.5, max_gap: int = 20,
        grid: int = 3, provider: str = "gemini", model: str | None = None,
        describe_frames: bool = True, force: bool = False,
        log: Callable[[str], None] = print) -> Path:
    """Run the whole pipeline on a local video file. Returns its cache folder."""
    video = Path(path).expanduser().resolve()
    if not video.is_file():
        raise FileNotFoundError(f"No file at {video}")

    workdir = CACHE / source.video_key(video)
    if (workdir / "timeline.json").exists() and not force:
        log("already processed, loading saved timeline")
        return workdir
    workdir.mkdir(parents=True, exist_ok=True)

    info = source.probe(video)
    log(f"{video.name}: {info['duration'] // 60} min {info['duration'] % 60} s")

    def speech() -> list[tuple[float, str]]:
        if not info["has_audio"]:
            log("no audio track")
            return []
        if not has_key("gemini"):
            log("no GEMINI_API_KEY set: skipping transcription")
            return []
        chunks = source.audio_chunks(video, workdir / "audio")
        log(f"transcribing {len(chunks)} audio piece(s)")
        cues = transcribe.transcribe(chunks, source.CHUNK_SECONDS)
        log(f"transcribed {len(cues)} lines of speech")
        return cues

    # Transcription waits on the network, frame scanning on the CPU: run both at once.
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(speech)
        log("looking for frames that change")
        thumbs = frames.thumbnails(video)
        cues = pending.result()

    chosen = frames.select(thumbs, cues, budget, threshold, max_gap)
    log(f"kept {len(chosen)} of {len(thumbs)} seconds")
    frame_paths = frames.extract(video, chosen, workdir / "frames")
    sheet_list = sheets.build(frame_paths, workdir / "sheets", grid)

    visuals = []
    if not describe_frames:
        log("skipping frame notes")
    elif not has_key(provider):
        log(f"no {KEYS[provider][0]} set: skipping frame notes")
    else:
        model = model or describe.PROVIDERS[provider][1]
        log(f"describing {len(sheet_list)} contact sheets with {model}")
        visuals = describe.describe(sheet_list, cues, provider, model)
        log(f"got {len(visuals)} notes about the screen")

    meta = {"id": workdir.name, "title": video.name, "source": str(video), "duration": info["duration"]}
    items = timeline.entries(cues, visuals)
    timeline.write(meta, items, [sheets.seconds_of(f) for f in frame_paths], workdir)
    log("done")
    return workdir


def watch(args: argparse.Namespace) -> None:
    started = time.time()
    workdir = run(
        args.file, budget=args.budget, threshold=args.threshold, max_gap=args.max_gap,
        grid=args.grid, provider=args.provider, model=args.model,
        describe_frames=not args.no_describe, force=args.force,
        log=lambda msg: print(f"[{time.time() - started:5.1f}s] {msg}", file=sys.stderr),
    )
    print(workdir / "timeline.md")


def serve(args: argparse.Namespace) -> None:
    from .server import start

    start(args.port, open_browser=not args.no_browser)


def mcp(args: argparse.Namespace) -> None:
    from .mcp_server import server

    server.run("stdio")


def main() -> None:
    parser = argparse.ArgumentParser(prog="flipframe", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    w = sub.add_parser("watch", help="turn a video file into a text timeline")
    w.add_argument("file")
    w.add_argument("--budget", type=int, default=90, help="max frames to keep (default 90)")
    w.add_argument("--threshold", type=float, default=0.5,
                   help="percent of the picture that must change to keep a frame (default 0.5)")
    w.add_argument("--max-gap", type=int, default=20,
                   help="always keep a frame at least this often, seconds (default 20)")
    w.add_argument("--grid", type=int, default=3, choices=[1, 2, 3, 4],
                   help="frames per sheet side; 2 shows small text bigger (default 3)")
    w.add_argument("--provider", choices=describe.PROVIDERS, default="gemini",
                   help="who describes the frames (default gemini)")
    w.add_argument("--model", help="override the frame-notes model")
    w.add_argument("--no-describe", action="store_true", help="skip notes about the frames")
    w.add_argument("--force", action="store_true", help="reprocess even if cached")
    w.set_defaults(func=watch)

    s = sub.add_parser("serve", help="open the web page")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    s.set_defaults(func=serve)

    m = sub.add_parser("mcp", help="run as an MCP server over stdio")
    m.set_defaults(func=mcp)

    load_env()
    args = parser.parse_args()
    args.func(args)
