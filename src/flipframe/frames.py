"""Step 3: keep only the frames that carry new information."""

import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

THUMB = 32

# Speech that points at the screen: the payload is in the picture, not the words.
POINTING = re.compile(
    r"\b(as you can see|you can see|right here|over here|look at|take a look|"
    r"notice|watch this|like this|like that|this one|see here)\b",
    re.IGNORECASE,
)


def thumbnails(video: Path) -> np.ndarray:
    """One 32x32 grayscale thumbnail per second of video, shape (seconds, 32, 32)."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", f"fps=1,scale={THUMB}:{THUMB},format=gray",
         "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, THUMB, THUMB).astype(np.int16)


def select(thumbs: np.ndarray, cues: list[tuple[float, str]],
           budget: int, threshold: float, max_gap: int) -> list[int]:
    """Pick the seconds worth looking at.

    A frame is kept when it differs enough from the last *kept* frame (so slow
    changes like typing still add up), when the speaker points at the screen,
    or when nothing has been kept for max_gap seconds.
    """
    pointing = {int(t) for t, text in cues if POINTING.search(text)}
    kept: list[tuple[int, float]] = []  # (second, how much it changed)
    last = None
    for t, thumb in enumerate(thumbs):
        if thumb.mean() < 8:  # black frame / fade
            continue
        change = 255.0 if last is None else float(np.abs(thumb - last).mean())
        gap = t - kept[-1][0] if kept else max_gap
        if change > threshold or gap >= max_gap or (t in pointing and gap >= 2):
            kept.append((t, change))
            last = thumb

    if len(kept) > budget:  # over budget: keep the biggest changes
        kept = sorted(kept, key=lambda k: -k[1])[:budget]
    return sorted(t for t, _ in kept)


def extract(video: Path, seconds: list[int], out: Path) -> list[Path]:
    """Save the chosen seconds as full-quality JPEGs named by timestamp."""
    out.mkdir(exist_ok=True)
    paths = []
    for t in seconds:
        p = out / f"{t:05d}.jpg"
        if not p.exists():
            subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video),
                 "-frames:v", "1", "-q:v", "3", "-y", str(p)],
                check=True,
            )
        if not p.exists():
            continue
        if np.asarray(Image.open(p).convert("L")).mean() < 8:  # seek landed on a black frame
            p.unlink()
            continue
        paths.append(p)
    return paths
