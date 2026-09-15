"""FlipFrame: flip through a YouTube video and keep the frames that matter."""

import argparse
import os
import sys
import time
from pathlib import Path

from . import describe, fetch, frames, sheets, timeline

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
    meta = fetch.fetch(args.url, workdir)
    cues = fetch.parse_vtt(meta["subs"]) if meta["subs"] else []
    log(f"{meta['title']!r}: {meta['duration']}s, {len(cues)} subtitle lines")

    thumbs = frames.thumbnails(meta["video"])
    chosen = frames.select(thumbs, cues, args.budget, args.threshold, args.max_gap)
    log(f"kept {len(chosen)} of {len(thumbs)} seconds")

    frame_paths = frames.extract(meta["video"], chosen, workdir / "frames")
    sheet_list = sheets.build(frame_paths, workdir / "sheets")
    log(f"built {len(sheet_list)} contact sheets")

    visuals = []
    if args.no_describe:
        log("skipping descriptions (--no-describe)")
    elif not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        log("no ANTHROPIC_API_KEY set: skipping descriptions, sheets are still saved")
    else:
        log(f"describing sheets with {args.model}")
        visuals = describe.describe(sheet_list, cues, args.model)
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
    w.add_argument("--threshold", type=float, default=12.0,
                   help="how different a frame must be to keep, 0-255 (default 12)")
    w.add_argument("--max-gap", type=int, default=20,
                   help="always keep a frame at least this often, seconds (default 20)")
    w.add_argument("--model", default="claude-haiku-4-5", help="model for descriptions")
    w.add_argument("--no-describe", action="store_true", help="stop after building contact sheets")
    w.add_argument("--force", action="store_true", help="rebuild even if cached")
    w.set_defaults(func=watch)

    args = parser.parse_args()
    args.func(args)
