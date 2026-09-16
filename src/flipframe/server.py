"""Local web page for FlipFrame."""

import json
import os
import re
import shutil
import threading
import time
import uuid
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import CACHE, PROJECT, chat, has_key, load, run, source

WEB = Path(__file__).parent / "web"
PAGE = WEB / "index.html"
UPLOADS = CACHE / "uploads"
SAMPLES = Path(os.environ.get("FLIPFRAME_SAMPLES", PROJECT / "test-videos"))
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
VIDEO_ID = re.compile(r"^[0-9a-f]{12}$")
FRAME = re.compile(r"^\d{5}\.jpg$")

app = FastAPI()
app.mount("/vendor", StaticFiles(directory=WEB / "vendor"), name="vendor")
app.mount("/models", StaticFiles(directory=WEB / "models"), name="models")
jobs: dict[str, dict] = {}


class WatchRequest(BaseModel):
    video: str
    coding: bool = False


class SampleRequest(BaseModel):
    name: str
    coding: bool = False


class ChatMessage(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


def _start_job(path: Path, coding: bool, force: bool, upload: Path | None = None) -> str:
    job_id = uuid.uuid4().hex[:8]
    job = jobs[job_id] = {"status": "running", "log": [], "video": None, "error": None}

    def work() -> None:
        try:
            workdir = run(path, grid=2 if coding else 3, force=force, log=job["log"].append)
            data = load(workdir.name)
            if upload and data and Path(data["source"]) != upload.resolve():
                shutil.rmtree(upload.parent, ignore_errors=True)  # same file was uploaded before
            job["video"], job["status"] = workdir.name, "done"
        except Exception as e:  # show the reason on the page instead of a silent failure
            if upload:
                shutil.rmtree(upload.parent, ignore_errors=True)
            job["error"], job["status"] = (str(e).strip().splitlines() or [type(e).__name__])[-1][:300], "error"

    threading.Thread(target=work, daemon=True).start()
    return job_id


def page(name: str, headers: dict | None = None) -> HTMLResponse:
    return HTMLResponse((WEB / name).read_text(encoding="utf-8"), headers=headers)


# Letting the speech model use several threads needs these two headers on every file it touches.
ISOLATION = {"Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "require-corp"}


@app.get("/", response_class=HTMLResponse)
@app.get("/about", response_class=HTMLResponse)
def landing_page() -> HTMLResponse:
    """What FlipFrame is and how to use it."""
    return page("landing.html")


@app.get("/app", response_class=HTMLResponse)
@app.get("/share", response_class=HTMLResponse)
def share_page() -> HTMLResponse:
    """The tool: picks frames on this device, nothing is uploaded."""
    return page("share.html", ISOLATION)


@app.get("/local", response_class=HTMLResponse)
def local_page() -> HTMLResponse:
    """The pipeline that runs on this machine: upload, frames, timeline."""
    return page("index.html")


@app.get("/worker.js")
def worker() -> FileResponse:
    return FileResponse(WEB / "worker.js", media_type="text/javascript", headers=ISOLATION)


@app.post("/api/upload")
async def upload(request: Request, name: str, coding: bool = False) -> dict:
    """Receive a video file as the raw request body, then process it."""
    safe = re.sub(r"[^\w.\- ]", "_", Path(name).name).strip() or "video"
    folder = UPLOADS / uuid.uuid4().hex[:8]
    folder.mkdir(parents=True)
    path = folder / safe
    size = 0
    with path.open("wb") as f:
        async for chunk in request.stream():
            f.write(chunk)
            size += len(chunk)
    if not size:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(400, "The file was empty.")
    return {"job": _start_job(path, coding, force=False, upload=path)}


@app.get("/api/samples")
def samples() -> list[dict]:
    """Video files in the test-videos folder, and whether each was processed already."""
    if not SAMPLES.is_dir():
        return []
    found = []
    for path in sorted(SAMPLES.iterdir()):
        if path.is_file() and path.suffix.lower() in VIDEO_EXT:
            key = source.video_key(path)
            found.append({"name": path.name, "size": path.stat().st_size,
                          "video": key if load(key) else None})
    return found


@app.post("/api/samples")
def process_sample(req: SampleRequest) -> dict:
    path = SAMPLES / Path(req.name).name
    if Path(req.name).name != req.name or not path.is_file() or path.suffix.lower() not in VIDEO_EXT:
        raise HTTPException(404, "No such test video")
    return {"job": _start_job(path, req.coding, force=False)}


@app.post("/api/watch")
def rewatch(req: WatchRequest) -> dict:
    """Reprocess a video that was watched before."""
    data = video(req.video)
    path = Path(data["source"])
    if not path.is_file():
        raise HTTPException(410, "The original file is gone, so it can't be processed again.")
    return {"job": _start_job(path, req.coding, force=True)}


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(404, "No such job. The server may have restarted; start again.")
    return jobs[job_id]


@app.get("/api/videos")
def videos() -> list[dict]:
    found = []
    for path in CACHE.glob("*/timeline.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "source" in data:
            found.append({"id": data["id"], "title": data["title"], "duration": data["duration"],
                          "watched": path.stat().st_mtime})
    return sorted(found, key=lambda v: -v["watched"])


@app.get("/api/videos/{video_id}")
def video(video_id: str) -> dict:
    data = load(video_id) if VIDEO_ID.match(video_id) else None
    if not data or "source" not in data:
        raise HTTPException(404, "Video not found")
    data["playable"] = Path(data["source"]).is_file()
    return data


@app.get("/media/{video_id}")
def media(video_id: str) -> FileResponse:
    path = Path(video(video_id)["source"])
    if not path.is_file():
        raise HTTPException(404, "The original video file is gone")
    return FileResponse(path)


@app.post("/api/videos/{video_id}/chat")
def ask(video_id: str, req: ChatRequest) -> StreamingResponse:
    data = video(video_id)
    messages = [m.model_dump() for m in req.messages][-20:]
    if not messages or messages[-1]["role"] != "user" or not messages[-1]["text"].strip():
        raise HTTPException(400, "Ask a question first.")
    if any(m["role"] not in ("user", "model") or len(m["text"]) > 8000 for m in messages):
        raise HTTPException(400, "Each message must be from user or model and under 8000 characters.")
    if not has_key("gemini"):
        raise HTTPException(400, "Chat needs GEMINI_API_KEY in .env.")

    def body():
        try:
            yield from chat.stream(CACHE / video_id, data, messages)
        except Exception as e:  # the page is already streaming, so report the error inline
            yield f"\n\n(Error from the model: {str(e).strip().splitlines()[-1][:300]})"

    return StreamingResponse(body(), media_type="text/plain; charset=utf-8")


@app.get("/frames/{video_id}/{name}")
def frame(video_id: str, name: str) -> FileResponse:
    path = CACHE / video_id / "frames" / name
    if not (VIDEO_ID.match(video_id) and FRAME.match(name) and path.exists()):
        raise HTTPException(404, "Frame not found")
    return FileResponse(path, headers={"Cache-Control": "max-age=86400"})


def start(port: int, open_browser: bool = True) -> None:
    url = f"http://127.0.0.1:{port}"
    print(f"FlipFrame   {url}\nThe tool    {url}/app\nLocal tools {url}/local")
    if open_browser:
        threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(url)), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
