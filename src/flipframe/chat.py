"""Answer questions about a watched video from its timeline and frames."""

import re
from collections.abc import Iterator
from pathlib import Path

from .describe import PROVIDERS
from .sheets import stamp

MODEL = PROVIDERS["gemini"][1]  # same fast model that describes the frames
MAX_FRAMES = 4

SYSTEM = """You answer questions about one YouTube video. You cannot play the video. \
You have its timeline instead: subtitles (SPEECH) and notes about what was on \
screen (SCREEN, TEXT, ACTION), each with a [MM:SS] timestamp. When the question \
names a moment, frames from around that moment are attached too.

Answer only from the timeline and the attached frames. Cite the moments you rely \
on as [MM:SS]. If the timeline does not cover something, say so plainly instead \
of guessing. Keep answers short unless asked for detail. Summarize what people \
say rather than quoting long stretches of the subtitles.

Formatting: plain sentences, or a simple list with "- " bullets. At most one level \
of sub-bullets, no headings, no tables. Put the timestamp where each point starts \
at the end of the point, like [04:12]; use a range like [04:12-05:30] only when \
the point covers a long stretch."""

TIME = re.compile(r"\b(\d{1,2}):([0-5]\d)\b")


def timeline_text(data: dict) -> str:
    lines = [f"Title: {data['title']}", f"Length: {stamp(data['duration'])}", ""]
    lines += [f"[{stamp(e['t'])}] {e['kind']} {e['text']}" for e in data["entries"]]
    return "\n".join(lines)


def frames_for(question: str, frame_seconds: list[int]) -> list[int]:
    """Kept frames closest to each timestamp mentioned in the question."""
    picked: list[int] = []
    for m, s in TIME.findall(question):
        if not frame_seconds:
            break
        t = int(m) * 60 + int(s)
        nearest = min(frame_seconds, key=lambda f: abs(f - t))
        if nearest not in picked:
            picked.append(nearest)
    return picked[:MAX_FRAMES]


def stream(workdir: Path, data: dict, messages: list[dict]) -> Iterator[str]:
    from google import genai
    from google.genai import types

    client = genai.Client()
    question = messages[-1]["text"]

    contents = [types.Content(role=m["role"], parts=[types.Part.from_text(text=m["text"])])
                for m in messages[:-1]]
    parts = []
    for t in frames_for(question, data["frames"]):
        path = workdir / "frames" / f"{t:05d}.jpg"
        if path.exists():
            parts += [types.Part.from_text(text=f"Frame at [{stamp(t)}]:"),
                      types.Part.from_bytes(data=path.read_bytes(), mime_type="image/jpeg")]
    parts.append(types.Part.from_text(text=question))
    contents.append(types.Content(role="user", parts=parts))

    config = types.GenerateContentConfig(
        system_instruction=f"{SYSTEM}\n\n<timeline>\n{timeline_text(data)}\n</timeline>",
        max_output_tokens=4000,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    for chunk in client.models.generate_content_stream(model=MODEL, contents=contents, config=config):
        if chunk.text:
            yield chunk.text
