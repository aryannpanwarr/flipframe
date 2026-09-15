# FlipFrame

Give a model the ability to watch a video file.

FlipFrame turns a local video into a timestamped timeline of what was **said** (transcribed
from the audio) and what was **shown** (notes on the frames that changed), and lets a model
look at the actual frames when it needs detail. You supply the video; FlipFrame never
downloads anything.

## Setup

```bash
uv sync
echo 'GEMINI_API_KEY=your-key' > .env
```

Needs `ffmpeg` on your PATH.

## Use it as an MCP tool

Add it to Claude Code (drop `--scope user` to enable it for one project only):

```bash
claude mcp add flipframe --scope user -- uv --directory /absolute/path/to/flipframe run flipframe mcp
```

Other MCP clients, e.g. Claude Desktop's `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "flipframe": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/flipframe", "run", "flipframe", "mcp"]
    }
  }
}
```

Tools:

| Tool | What it does |
|---|---|
| `watch_video(path, coding?, force?)` | Process a video file (or load it from cache) and return the timeline |
| `get_frames(video, timestamps)` | Return the actual picture at up to 6 moments, e.g. `["4:12", "7:30"]` |
| `get_timeline(video, start?, end?, kinds?)` | Read part of a long timeline, e.g. only `TEXT` between `10:00` and `20:00` |
| `list_videos()` | Videos already watched |

Set `coding: true` for videos with code or small text.

## Web page

```bash
uv run flipframe serve        # opens http://127.0.0.1:8765
```

Drop a video file in. You get a player, the kept frames, the timeline, and a chat about the
video. Click any timestamp to play from there.

## Command line

```bash
uv run flipframe watch path/to/video.mp4            # prints the path to timeline.md
uv run flipframe watch talk.mp4 --grid 2            # code or small text on screen
```

| Flag | Default | Meaning |
|---|---|---|
| `--budget` | 90 | max frames to keep |
| `--threshold` | 0.5 | percent of the picture that must change since the last kept frame |
| `--max-gap` | 20 | always keep a frame at least every N seconds |
| `--grid` | 3 | frames per contact-sheet side; 2 shows each frame bigger |
| `--provider` | `gemini` | who writes the frame notes: `gemini` or `claude` |
| `--no-describe` | off | skip frame notes |
| `--force` | off | reprocess even if cached |

## How it works

1. **Speech**: ffmpeg pulls the audio out, splits it into 5-minute pieces, and Gemini
   (`gemini-3.5-flash-lite`) transcribes them in parallel with timestamps
2. **Frames** (at the same time): every second is shrunk to a 160×90 thumbnail; a frame is kept
   when enough of it changed since the last kept one, when the speaker points at the screen
   ("as you can see…"), or when nothing was kept for 20 s
3. **Contact sheets**: kept frames are tiled 3×3 (or 2×2) with timestamps burned in
4. **Frame notes**: Gemini describes each sheet, skipping what the speech already says
5. **Timeline**: speech and notes merged into `timeline.json` and `timeline.md`

## Cache

Everything lives in `~/.cache/flipframe/<id>/` (change with `FLIPFRAME_CACHE`). The id comes
from the file's contents, so the same file is only processed once wherever it's stored.

```
<id>/
  audio/        speech-quality audio pieces
  frames/       kept frames, named by second (00252.jpg = 04:12)
  closeups/     extra frames fetched by get_frames
  sheets/       contact sheets sent to the model
  timeline.json
  timeline.md
```

The original video is not copied; FlipFrame reads it from where it is. Web uploads are stored
in `~/.cache/flipframe/uploads/`.
