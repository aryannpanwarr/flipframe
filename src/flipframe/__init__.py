"""FlipFrame: flip through a YouTube video and keep the frames that matter."""

import argparse
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from . import describe, fetch, frames, sheets, timeline

KEYS = {"claude": ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"],
        "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"]}
CACHE = Path(os.environ.get("FLIPFRAME_CACHE", Path.home() / ".cache" / "flipframe"))


def run(url: str, *, budget: int = 90, threshold: float = 0.5, max_gap: int = 20,
        height: int = 360, grid: int = 3, provider: str = "gemini", model: str | None = None,
        describe_frames: bool = True, force: bool = False,
        log: Callable[[str], None] = print) -> Path:
    """Run the whole pipeline. Returns the video's cache folder."""
    vid = fetch.video_id(url)
    workdir = CACHE / (vid or "unknown")
    if vid and (workdir / "timeline.json").exists() and not force:
        log("already watched, loading saved timeline")
        return workdir
    workdir.mkdir(parents=True, exist_ok=True)

    log("downloading video and subtitles")
    meta = fetch.fetch(url, workdir, height)
    workdir = CACHE / meta["id"]  # URL we couldn't parse: trust yt-dlp's id
    cues = fetch.parse_vtt(meta["subs"]) if meta["subs"] else []
    log(f"{meta['title']}: {meta['duration'] // 60} min, {len(cues)} subtitle lines")

    log("looking for frames that change")
    thumbs = frames.thumbnails(meta["video"])
    chosen = frames.select(thumbs, cues, budget, threshold, max_gap)
    log(f"kept {len(chosen)} of {len(thumbs)} seconds")

    frame_paths = frames.extract(meta["video"], chosen, workdir / "frames")
    sheet_list = sheets.build(frame_paths, workdir / "sheets", grid)
    log(f"built {len(sheet_list)} contact sheets")

    visuals = []
    if not describe_frames:
        log("skipping descriptions")
    elif not any(os.environ.get(k) for k in KEYS[provider]):
        log(f"no {KEYS[provider][0]} set: skipping descriptions")
    else:
        model = model or describe.PROVIDERS[provider][1]
        log(f"describing frames with {model}")
        visuals = describe.describe(sheet_list, cues, provider, model)
        log(f"got {len(visuals)} visual notes")

    items = timeline.entries(cues, visuals)
    timeline.write(meta, items, [sheets.seconds_of(f) for f in frame_paths], workdir)
    log("done")
    return workdir


def watch(args: argparse.Namespace) -> None:
    started = time.time()
    workdir = run(
        args.url, budget=args.budget, threshold=args.threshold, max_gap=args.max_gap,
        height=args.height, grid=args.grid, provider=args.provider, model=args.model,
        describe_frames=not args.no_describe, force=args.force,
        log=lambda msg: print(f"[{time.time() - started:5.1f}s] {msg}", file=sys.stderr),
    )
    print(workdir / "timeline.md")


def serve(args: argparse.Namespace) -> None:
    from .server import start

    start(args.port, open_browser=not args.no_browser)


def main() -> None:
    parser = argparse.ArgumentParser(prog="flipframe", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    w = sub.add_parser("watch", help="turn a YouTube video into a text timeline")
    w.add_argument("url")
    w.add_argument("--budget", type=int, default=90, help="max frames to keep (default 90)")
    w.add_argument("--threshold", type=float, default=0.5,
                   help="percent of the picture that must change to keep a frame (default 0.5)")
    w.add_argument("--max-gap", type=int, default=20,
                   help="always keep a frame at least this often, seconds (default 20)")
    w.add_argument("--height", type=int, default=360,
                   help="download resolution; use 720 for small on-screen text (default 360)")
    w.add_argument("--grid", type=int, default=3, choices=[1, 2, 3, 4],
                   help="frames per sheet side; 2 shows text bigger (default 3)")
    w.add_argument("--provider", choices=describe.PROVIDERS, default="gemini",
                   help="who describes the frames (default gemini)")
    w.add_argument("--model", help="override the model (gemini: gemini-3.5-flash-lite, claude: claude-haiku-4-5)")
    w.add_argument("--no-describe", action="store_true", help="stop after building contact sheets")
    w.add_argument("--force", action="store_true", help="rebuild even if cached")
    w.set_defaults(func=watch)

    s = sub.add_parser("serve", help="open the web page")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    s.set_defaults(func=serve)

    load_dotenv(find_dotenv(usecwd=True))
    args = parser.parse_args()
    args.func(args)
