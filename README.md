# FlipFrame

Let Claude actually *watch* YouTube videos, not just read the transcript.

FlipFrame flips through a video, keeps the few frames that matter, and turns them
plus the subtitles into a short, timestamped text timeline.

## Usage

```bash
uv sync
export ANTHROPIC_API_KEY=...        # only needed for step 5
uv run flipframe watch "https://www.youtube.com/watch?v=VIDEO_ID"
```

Prints the path to `timeline.md`. Everything is cached in `~/.cache/flipframe/<video_id>/`
(change with `FLIPFRAME_CACHE`), so a second run on the same video is instant.

| Flag | Default | Meaning |
|---|---|---|
| `--budget` | 90 | max frames to keep |
| `--threshold` | 12 | how different (0–255) a frame must be from the last kept one |
| `--max-gap` | 20 | always keep a frame at least every N seconds |
| `--model` | `claude-haiku-4-5` | model that describes the frames |
| `--no-describe` | off | stop after contact sheets (no API key, no cost) |
| `--force` | off | rebuild even if cached |

Needs `ffmpeg` on your PATH.

## How it works

1. **Download** a 360p copy (no audio) with `yt-dlp`
2. **Subtitles**: grab YouTube's free captions
3. **Pick frames**: shrink every second to a 32×32 thumbnail and keep a frame when it differs
   from the last kept one, when the speaker points at the screen ("as you can see…"), or
   when nothing was kept for 20 s
4. **Contact sheets**: tile kept frames 3×3 with timestamps burned in
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
