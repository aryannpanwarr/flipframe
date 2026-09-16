# FlipFrame

Let an AI chat watch your video.

Claude and ChatGPT read text and look at pictures, but they can't watch video. FlipFrame turns a
video into the handful of frames that actually carry information, plus a transcript, and gives you
**one PDF to drop into the chat**.

There are two ways to use it:

| | Runs where | Good for |
|---|---|---|
| **Browser tool** | Entirely in the browser; the video is never uploaded | Any chat app, including on a phone |
| **MCP server + CLI** | On your machine | Claude Desktop and Claude Code, where the model calls it directly |

## Setup

```bash
uv sync
./scripts/fetch-models.sh        # Whisper models for in-browser speech (~117 MB, not in git)
uv run flipframe serve           # http://127.0.0.1:8765
```

Needs `ffmpeg` on your PATH. For the MCP server and the CLI, put `GEMINI_API_KEY=...` in `.env`.

Pages:

| Address | Page |
|---|---|
| `/` | Landing page |
| `/app` (or `/share`) | **The browser tool** |
| `/local` | Local pipeline: upload a video, play it, read its timeline |

## The browser tool

Pick a video, and the page:

1. **Finds the moments that change.** Every second is shrunk to a 160×90 thumbnail and compared with
   the last kept one. A frame is kept when enough of the picture changed, and never closer than 3 s
   apart unless the shot really cuts, so a talking face doesn't use up the budget.
2. **Crops each moment** to the part of the screen that changed, and grabs it a beat later so typing
   has finished.
3. **Writes down the speech**, either with Whisper running on your device (bundled, nothing leaves
   the machine) or through Google with your own key. Whichever you pick, the other is used
   automatically if it fails.
4. **Builds one PDF**: a first page explaining how to read it, then one page per moment — the
   close-up, then what was said until the next moment.

Then **Share** (straight into the Claude or ChatGPT app on a phone) or **Download**.

A 10-minute tutorial takes about 30 s for frames plus 15 s for speech through Google, and comes to
roughly 40 pages and 2 MB.

### Privacy

- The video never leaves your device. Frames, cropping and the PDF are all made in the page.
- Speech on device uses the bundled Whisper model and no network at all.
- Choosing Google sends only the audio, as small MP3 pieces, straight from your browser to Google.
- Your API key is kept for the tab only, unless you tick "Remember the key on this device".

## MCP server

Add it to Claude Code (drop `--scope user` for this project only):

```bash
claude mcp add flipframe --scope user -- uv --directory /absolute/path/to/flipframe run flipframe mcp
```

Claude Desktop's `claude_desktop_config.json`:

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

| Tool | What it does |
|---|---|
| `watch_video(path, coding?, force?)` | Process a video file (or load it from cache) and return its timeline |
| `get_frames(video, timestamps)` | Return the picture at up to 6 moments, e.g. `["4:12", "7:30"]` |
| `get_timeline(video, start?, end?, kinds?)` | Read part of a long timeline |
| `list_videos()` | Videos already watched |

The MCP server runs on your machine, so it needs the video's path. Phone and web chat apps can only
reach servers on the internet — use the browser tool there.

## Command line

```bash
uv run flipframe watch path/to/video.mp4      # prints the path to timeline.md
uv run flipframe watch talk.mp4 --grid 2      # code or small text on screen
```

| Flag | Default | Meaning |
|---|---|---|
| `--budget` | 90 | max frames to keep |
| `--threshold` | 0.5 | percent of the picture that must change since the last kept frame |
| `--max-gap` | 20 | always keep a frame at least every N seconds |
| `--min-gap` | 3 | never keep frames closer than this, unless the shot cuts |
| `--grid` | 3 | frames per contact-sheet side; 2 shows each frame bigger |
| `--provider` | `gemini` | who writes the frame notes: `gemini` or `claude` |
| `--no-describe` | off | skip frame notes |
| `--force` | off | reprocess even if cached |

The CLI and MCP path still produce contact sheets and a timeline; the crop-and-interleave layout
lives in the browser tool for now.

## Cache

Everything is kept in `~/.cache/flipframe/<id>/` (change with `FLIPFRAME_CACHE`). The id comes from
the file's contents, so the same video is only processed once wherever it is stored.

```
<id>/
  audio/        speech-quality audio pieces
  frames/       kept frames, named by second (00252.jpg = 04:12)
  closeups/     extra frames fetched by get_frames
  sheets/       contact sheets sent to the model
  timeline.json
  timeline.md
```

The original video is never copied; FlipFrame reads it where it is. Videos uploaded through `/local`
are stored in `~/.cache/flipframe/uploads/`.

## Known limits

- **Motion is lost.** Sport, dance and physical demos come out as stills; you learn where something
  happened, not how it moved.
- **Small on-screen text can still be hard to read.** Cropping helps a lot; reading the text out with
  OCR would help more and isn't built yet.
- **Long videos in the browser.** Audio is decoded in one piece, so very long videos can run out of
  memory on a phone. Whisper on a phone is also slow — use Google there.
- **Gaps between moments.** Small changes such as a line being typed can fall between frames. The
  PDF says so on its first page.

## Layout

```
src/flipframe/
  __init__.py      pipeline + CLI
  source.py        read a video file, pull out audio
  transcribe.py    audio -> timestamped text (Gemini)
  frames.py        pick and cut the frames that matter
  sheets.py        contact sheets
  describe.py      frame notes (Gemini or Claude)
  timeline.py      merge speech and notes
  server.py        local web server
  mcp_server.py    MCP tools
  web/             landing page, browser tool, local page, Whisper worker
scripts/
  fetch-models.sh  download the Whisper models
```
