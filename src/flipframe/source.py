"""Read a local video file: identify it, measure it, and pull its audio out."""

import hashlib
import json
import subprocess
from pathlib import Path

CHUNK_SECONDS = 300  # audio is transcribed in 5-minute pieces, in parallel


def video_key(path: Path) -> str:
    """Stable id from the file's size and its first and last megabyte.

    Fast even for huge files, and the same file gets the same id wherever it lives.
    """
    size = path.stat().st_size
    h = hashlib.sha1(str(size).encode())
    with path.open("rb") as f:
        h.update(f.read(1 << 20))
        if size > 2 << 20:
            f.seek(-(1 << 20), 2)
            h.update(f.read())
    return h.hexdigest()[:12]


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
         "-of", "json", str(path)],
        capture_output=True, check=True, text=True,
    ).stdout
    info = json.loads(out)
    kinds = {s.get("codec_type") for s in info.get("streams", [])}
    if "video" not in kinds:
        raise ValueError(f"{path.name} has no video track")
    return {
        "duration": int(float(info.get("format", {}).get("duration") or 0)),
        "has_audio": "audio" in kinds,
    }


def audio_chunks(video: Path, out: Path) -> list[tuple[int, Path]]:
    """Extract speech-quality audio and split it. Returns (start_second, file) pairs."""
    out.mkdir(exist_ok=True)
    for old in out.glob("chunk_*.mp3"):
        old.unlink()
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "libmp3lame", "-b:a", "32k",
         "-f", "segment", "-segment_time", str(CHUNK_SECONDS), "-reset_timestamps", "1",
         "-y", str(out / "chunk_%03d.mp3")],
        check=True,
    )
    chunks = sorted(out.glob("chunk_*.mp3"))
    return [(i * CHUNK_SECONDS, p) for i, p in enumerate(chunks)]
