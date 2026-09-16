"""Step 3: keep only the frames that carry new information."""

import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

THUMB_W, THUMB_H = 160, 90
PIXEL_CHANGED = 24  # a pixel counts as changed if its brightness moved this much (0-255)
BIG_CHANGE = 15.0   # percent changed that means a real scene cut, not someone talking

# Speech that points at the screen: the payload is in the picture, not the words.
POINTING = re.compile(
    r"\b(as you can see|you can see|right here|over here|look at|take a look|"
    r"notice|watch this|like this|like that|this one|see here)\b",
    re.IGNORECASE,
)


def thumbnails(video: Path) -> np.ndarray:
    """One 160x90 grayscale thumbnail per second of video, shape (seconds, 90, 160)."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", f"fps=1,scale={THUMB_W}:{THUMB_H},format=gray",
         "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, THUMB_H, THUMB_W).astype(np.int16)


def select(thumbs: np.ndarray, cues: list[tuple[float, str]],
           budget: int, threshold: float, max_gap: int, min_gap: int = 3) -> list[int]:
    """Pick the seconds worth looking at.

    A frame is kept when enough of it differs from the last *kept* frame (so
    slow changes like typing still add up), when the speaker points at the
    screen, or when nothing has been kept for max_gap seconds. threshold is the
    percent of pixels that must have changed: typing one line of code is ~0.5%.
    A talking face changes a little every second, so frames are never kept closer
    together than min_gap unless the picture changed enough to be a real cut.
    """
    pointing = {int(t) for t, text in cues if POINTING.search(text)}
    kept: list[int] = []
    last = None
    for t, thumb in enumerate(thumbs):
        if thumb.mean() < 8:  # black frame / fade
            continue
        changed = 100.0 if last is None else float((np.abs(thumb - last) > PIXEL_CHANGED).mean() * 100)
        gap = t - kept[-1] if kept else max_gap
        if ((changed > threshold and gap >= min_gap) or changed > BIG_CHANGE
                or gap >= max_gap or (t in pointing and gap >= min_gap)):
            kept.append(t)
            last = thumb

    if len(kept) > budget:  # busy video: spread the budget evenly over time
        step = len(kept) / budget
        kept = [kept[int(i * step)] for i in range(budget)]
    return kept


def extract(video: Path, seconds: list[int], out: Path, max_width: int = 1280) -> list[Path]:
    """Save the chosen seconds as JPEGs (at most max_width wide) named by timestamp."""
    out.mkdir(exist_ok=True)
    paths = []
    for t in seconds:
        p = out / f"{t:05d}.jpg"
        if not p.exists():
            subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video),
                 "-frames:v", "1", "-vf", f"scale='min({max_width},iw)':-2",
                 "-q:v", "3", "-y", str(p)],
                check=True,
            )
        if not p.exists():
            continue
        if np.asarray(Image.open(p).convert("L")).mean() < 8:  # seek landed on a black frame
            p.unlink()
            continue
        paths.append(p)
    return paths
