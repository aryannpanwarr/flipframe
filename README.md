# FlipFrame

Let Claude actually *watch* YouTube videos, not just read the transcript.

FlipFrame flips through a video, keeps the few frames that matter, and turns them
plus the subtitles into a short, timestamped text timeline.

## Plan

1. Download the video small (360p) with `yt-dlp`
2. Grab the free YouTube subtitles
3. Keep only the frames that changed (and moments the speaker points at: "as you can see…")
4. Tile kept frames into 3×3 contact sheets with timestamps
5. Describe each sheet once with a cheap model, skipping what the subtitles already say
6. Save `timeline.md` + frames to disk, so every later question is free

Status: planning.
