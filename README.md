# FlipFrame

Let Claude actually *watch* YouTube videos, not just read the transcript.

FlipFrame flips through a video, keeps the few frames that matter, and turns them
plus the subtitles into a short, timestamped text timeline.

## Usage

```bash
uv sync
# put GEMINI_API_KEY=... in .env (or ANTHROPIC_API_KEY for --provider claude)
uv run flipframe watch "https://www.youtube.com/watch?v=VIDEO_ID"
```

Prints the path to `timeline.md`. Everything is cached in `~/.cache/flipframe/<video_id>/`
(change with `FLIPFRAME_CACHE`), so a second run on the same video is instant.

| Flag | Default | Meaning |
|---|---|---|
| `--budget` | 90 | max frames to keep |
| `--threshold` | 0.5 | percent of the picture that must change since the last kept frame |
| `--max-gap` | 20 | always keep a frame at least every N seconds |
| `--height` | 360 | download resolution; use 720 for code or small text |
| `--grid` | 3 | frames per sheet side; 2 shows each frame bigger |
| `--provider` | `gemini` | `gemini` or `claude` |
| `--model` | `gemini-3.5-flash-lite` / `claude-haiku-4-5` | override the model |
| `--no-describe` | off | stop after contact sheets (no API key, no cost) |
| `--force` | off | rebuild even if cached |

Needs `ffmpeg` on your PATH.

For coding videos: `--height 720 --grid 2` (otherwise small symbols like quote marks get lost).

## How it works

1. **Download** a small copy (no audio) with `yt-dlp`
2. **Subtitles**: grab YouTube's free captions
3. **Pick frames**: shrink every second to a 160×90 thumbnail and keep a frame when enough of it
   differs from the last kept one, when the speaker points at the screen ("as you can see…"), or
   when nothing was kept for 20 s
4. **Contact sheets**: tile kept frames 3×3 (or 2×2) with timestamps burned in
5. **Describe** each sheet with a cheap model, told to skip what the subtitles already say
6. **Timeline**: merge speech + visuals into `timeline.md`; frames stay on disk for close-ups

## Cache layout

```
~/.cache/flipframe/<video_id>/
  video.mp4          360p copy
  video.en.vtt       subtitles
  frames/00252.jpg   kept frames, named by second (00252 = 04:12)
  sheets/            contact sheets sent to the model
  timeline.md        the result
```
