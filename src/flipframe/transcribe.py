"""Speech to timestamped text with Gemini."""

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MODEL = "gemini-3.5-flash-lite"  # same fast model as the frame notes; accepts audio

PROMPT = """Transcribe all speech in this audio clip, in its original language.

Output one line per sentence or short phrase, formatted exactly as:
MM:SS text
where MM:SS is when that phrase starts, counted from the start of this clip.

Output nothing else: no title, no notes, no speaker labels unless a name is spoken. \
If there is no speech, output nothing."""

LINE = re.compile(r"^\[?\s*(\d{1,2}):([0-5]\d)\s*\]?\s*[-–|:]?\s*(.+)$")


def _one(client, start: int, path: Path, length: int) -> list[tuple[float, str]]:
    from google.genai import types

    resp = client.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=path.read_bytes(), mime_type="audio/mp3"), PROMPT],
        config=types.GenerateContentConfig(
            max_output_tokens=16000,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    cues = []
    for line in (resp.text or "").splitlines():
        m = LINE.match(line.strip())
        if m:
            t = min(int(m.group(1)) * 60 + int(m.group(2)), length)
            cues.append((float(start + t), m.group(3).strip()))
    return cues


def transcribe(chunks: list[tuple[int, Path]], chunk_seconds: int) -> list[tuple[float, str]]:
    if not chunks:
        return []
    from google import genai

    client = genai.Client()
    with ThreadPoolExecutor(min(8, len(chunks))) as pool:
        parts = pool.map(lambda c: _one(client, c[0], c[1], chunk_seconds), chunks)
        return sorted(cue for part in parts for cue in part)
