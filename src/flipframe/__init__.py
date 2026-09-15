"""FlipFrame: flip through a YouTube video and keep the frames that matter."""

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from . import describe, fetch, frames, sheets, timeline

KEYS = {"claude": ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"],
        "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"]}
CACHE = Path(os.environ.get("FLIPFRAME_CACHE", Path.home() / ".cache" / "flipframe"))


def watch(args: argparse.Namespace) -> None:
    vid = fetch.video_id(args.url)
    workdir = CACHE / (vid or "unknown")
    out = workdir / "timeline.md"
    if vid and out.exists() and not args.force:
        print(out)
        return
    workdir.mkdir(parents=True, exist_ok=True)

    started = time.time()
    log = lambda msg: print(f"[{time.time() - started:5.1f}s] {msg}", file=sys.stderr)

    log("downloading video and subtitles")
    meta = fetch.fetch(args.url, workdir, args.height)
    cues = fetch.parse_vtt(meta["subs"]) if meta["subs"] else []
    log(f"{meta['title']!r}: {meta['duration']}s, {len(cues)} subtitle lines")

    thumbs = frames.thumbnails(meta["video"])
    chosen = frames.select(thumbs, cues, args.budget, args.threshold, args.max_gap)
    log(f"kept {len(chosen)} of {len(thumbs)} seconds")

    frame_paths = frames.extract(meta["video"], chosen, workdir / "frames")
    sheet_list = sheets.build(frame_paths, workdir / "sheets", args.grid)
    log(f"built {len(sheet_list)} contact sheets")

    visuals = []
    if args.no_describe:
        log("skipping descriptions (--no-describe)")
    elif not any(os.environ.get(k) for k in KEYS[args.provider]):
        log(f"no {KEYS[args.provider][0]} set: skipping descriptions, sheets are still saved")
    else:
        model = args.model or describe.PROVIDERS[args.provider][1]
        log(f"describing sheets with {args.provider} {model}")
        visuals = describe.describe(sheet_list, cues, args.provider, model)
        log(f"got {len(visuals)} visual lines")

    timeline.write(meta, cues, visuals, workdir / "frames", out)
    log("done")
    print(out)


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

    load_dotenv()  # .env in the current directory or any parent
    args = parser.parse_args()
    args.func(args)
