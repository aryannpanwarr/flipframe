"""Step 5: turn contact sheets into text, skipping what the subtitles already say."""

import base64
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from .sheets import stamp

SYSTEM = """You are turning a video into a text timeline for someone who cannot see it.

You get one contact sheet: up to 9 frames from the video, left to right, top to \
bottom, each labeled with its timestamp in yellow. You also get the subtitles \
spoken during that stretch.

Describe only what the pictures add beyond the subtitles: what is on screen, \
any readable text or code (quote it exactly), diagrams, charts, what people \
are doing or pointing at. Do not repeat what the subtitles already say. \
Skip a frame entirely if it adds nothing new over the previous frame.

Output one line per useful frame, nothing else:
MM:SS | KIND | description
KIND is SCREEN (what is shown), TEXT (readable on-screen text or code, quoted), \
or ACTION (what someone does). A frame may have more than one line."""

LINE = re.compile(r"^\[?(\d+):(\d\d)\]?\s*\|\s*(SCREEN|TEXT|ACTION)\s*\|\s*(.+)$")


def _describe_one(client: anthropic.Anthropic, model: str, sheet: Path,
                  seconds: list[int], cues: list[tuple[float, str]]) -> list[tuple[int, str, str]]:
    lo, hi = seconds[0] - 10, seconds[-1] + 10
    speech = "\n".join(f"{stamp(int(t))} {text}" for t, text in cues if lo <= t <= hi)
    image = base64.standard_b64encode(sheet.read_bytes()).decode()

    msg = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image}},
                {"type": "text", "text": f"Frames on this sheet: {', '.join(stamp(s) for s in seconds)}\n\n"
                                         f"Subtitles for this stretch:\n{speech or '(none)'}"},
            ],
        }],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    out = []
    for line in text.splitlines():
        m = LINE.match(line.strip())
        if m:
            mi, s, kind, desc = m.groups()
            out.append((int(mi) * 60 + int(s), kind, desc.strip()))
    return out


def describe(sheets: list[tuple[Path, list[int]]], cues: list[tuple[float, str]],
             model: str, workers: int = 4) -> list[tuple[int, str, str]]:
    client = anthropic.Anthropic()
    with ThreadPoolExecutor(workers) as pool:
        results = pool.map(lambda sh: _describe_one(client, model, sh[0], sh[1], cues), sheets)
        return [entry for batch in results for entry in batch]
