"""Local web page for FlipFrame."""

import json
import os
import re
import threading
import time
import uuid
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from . import CACHE, chat, run

PAGE = Path(__file__).parent / "web" / "index.html"
VIDEO_ID = re.compile(r"^[\w-]{6,20}$")
FRAME = re.compile(r"^\d{5}\.jpg$")

app = FastAPI()
jobs: dict[str, dict] = {}


class WatchRequest(BaseModel):
    url: str
    coding: bool = False
    force: bool = False


class ChatMessage(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return PAGE.read_text(encoding="utf-8")


@app.post("/api/watch")
def watch(req: WatchRequest) -> dict:
    job_id = uuid.uuid4().hex[:8]
    job = jobs[job_id] = {"status": "running", "log": [], "video": None, "error": None}

    def work() -> None:
        try:
            options = {"height": 720, "grid": 2} if req.coding else {}
            workdir = run(req.url, force=req.force, log=job["log"].append, **options)
            job["video"], job["status"] = workdir.name, "done"
        except Exception as e:  # show the reason on the page instead of a silent failure
            job["error"], job["status"] = str(e).strip().splitlines()[-1][:300], "error"

    threading.Thread(target=work, daemon=True).start()
    return {"job": job_id}


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
        found.append({"id": data["id"], "title": data["title"], "duration": data["duration"],
                      "watched": path.stat().st_mtime})
    return sorted(found, key=lambda v: -v["watched"])


@app.get("/api/videos/{video_id}")
def video(video_id: str) -> dict:
    path = CACHE / video_id / "timeline.json"
    if not VIDEO_ID.match(video_id) or not path.exists():
        raise HTTPException(404, "Video not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/videos/{video_id}/chat")
def ask(video_id: str, req: ChatRequest) -> StreamingResponse:
    data = video(video_id)
    messages = [m.model_dump() for m in req.messages][-20:]
    if not messages or messages[-1]["role"] != "user" or not messages[-1]["text"].strip():
        raise HTTPException(400, "Ask a question first.")
    if any(m["role"] not in ("user", "model") or len(m["text"]) > 8000 for m in messages):
        raise HTTPException(400, "Each message must be from user or model and under 8000 characters.")
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
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
    print(f"FlipFrame running at {url}")
    if open_browser:
        threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(url)), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
