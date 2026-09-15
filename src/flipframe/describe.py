"""Step 5: turn contact sheets into text, skipping what the subtitles already say."""

import base64
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .sheets import stamp

SYSTEM = """You are turning a video into a text timeline for someone who cannot see it.

You get one contact sheet: up to 9 frames from the video, left to right, top to \
bottom, each labeled with its timestamp in yellow. You also get the subtitles \
spoken during that stretch.

Describe only what the pictures add beyond the subtitles: what is on screen, \
any readable text or code, diagrams, charts, what people are doing or pointing \
at. Do not repeat what the subtitles already say.

Only report what is new compared with the previous frame. If code or text was \
already quoted for an earlier frame, quote only the lines that were added or \
changed. Skip a frame entirely if nothing new appears. Ignore half-typed lines \
unless nothing else changed. Copy text character for character, keeping every quote \
mark, bracket and symbol; do not wrap it in backticks or markdown. Put several \
lines of code on one TEXT line separated by " ⏎ ".

Output one line per useful frame, nothing else:
MM:SS | KIND | description
KIND is SCREEN (what is shown), TEXT (readable on-screen text or code, quoted), \
or ACTION (what someone does). A frame may have more than one line."""

LINE = re.compile(r"^\[?(\d+):(\d\d)\]?\s*\|\s*(SCREEN|TEXT|ACTION)\s*\|\s*(.+)$")


def _prompt(seconds: list[int], cues: list[tuple[float, str]]) -> str:
    lo, hi = seconds[0] - 10, seconds[-1] + 10
    speech = "\n".join(f"{stamp(int(t))} {text}" for t, text in cues if lo <= t <= hi)
    return (f"Frames on this sheet: {', '.join(stamp(s) for s in seconds)}\n\n"
            f"Subtitles for this stretch:\n{speech or '(none)'}")


def _parse(text: str) -> list[tuple[int, str, str]]:
    out = []
    for line in text.splitlines():
        m = LINE.match(line.strip().strip("`*-").strip())
        if m:
            mi, s, kind, desc = m.groups()
            out.append((int(mi) * 60 + int(s), kind, desc.strip()))
    return out


def _claude(model: str):
    import anthropic

    client = anthropic.Anthropic()

    def call(sheet: Path, prompt: str) -> str:
        image = base64.standard_b64encode(sheet.read_bytes()).decode()
        msg = client.messages.create(
            model=model,
            max_tokens=2000,
            system=SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return "".join(b.text for b in msg.content if b.type == "text")

    return call


def _gemini(model: str):
    from google import genai
    from google.genai import types

    client = genai.Client()  # reads GEMINI_API_KEY
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        max_output_tokens=4000,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    def call(sheet: Path, prompt: str) -> str:
        resp = client.models.generate_content(
            model=model,
            contents=[types.Part.from_bytes(data=sheet.read_bytes(), mime_type="image/jpeg"), prompt],
            config=config,
        )
        return resp.text or ""

    return call


PROVIDERS = {"claude": (_claude, "claude-haiku-4-5"), "gemini": (_gemini, "gemini-3.5-flash-lite")}


def describe(sheets: list[tuple[Path, list[int]]], cues: list[tuple[float, str]],
             provider: str, model: str, workers: int = 4) -> list[tuple[int, str, str]]:
    make, _ = PROVIDERS[provider]
    call = make(model)
    with ThreadPoolExecutor(workers) as pool:
        texts = pool.map(lambda sh: call(sh[0], _prompt(sh[1], cues)), sheets)
        return [entry for text in texts for entry in _parse(text)]
