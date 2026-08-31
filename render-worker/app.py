"""HTTP wrapper around the existing render pipeline (main.py), designed to run
persistently on a VM instead of as a Render web-service subprocess -- so a long
render is never killed by a platform health-check restart mid-flight.

Job status is written to a JSON file per job (not just kept in memory), so a
client polling for status gets a clear answer even if this process restarts.
"""

import json
import logging
import os
import secrets
import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

# main.py, config.py, video.py, tts.py, pexels.py, and giphy.py are copied
# into this same directory at image build time (see render-worker/Dockerfile)
# so these are plain same-directory imports, not a separate package.
from config import project_dir
from giphy import GiphyError
from main import load_script, process
from pexels import PexelsError
from tts import TTSError
from video import FFmpegError

app = FastAPI(title="Empire Render Worker")
logger = logging.getLogger(__name__)

# Auth is optional, same pattern as the TTS service: enforced if
# RENDER_SERVICE_TOKEN is set, open to anyone with the URL if it's blank.
TOKEN = os.getenv("RENDER_SERVICE_TOKEN", "").strip()
if not TOKEN:
    logger.warning("RENDER_SERVICE_TOKEN not set -- render worker is open to anyone with the URL")

JOBS_DIR = Path(os.getenv("RENDER_JOBS_DIR", "/app/jobs"))
JOBS_DIR.mkdir(parents=True, exist_ok=True)


class RenderRequest(BaseModel):
    script: dict


def _check_token(x_render_token: str | None) -> None:
    if TOKEN and (not x_render_token or not secrets.compare_digest(x_render_token, TOKEN)):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _job_path(job_id: str) -> Path:
    # job_id is always our own uuid4().hex -- never derived from user input --
    # so this can't be used to escape JOBS_DIR.
    return JOBS_DIR / f"{job_id}.json"


def _write_status(job_id: str, **fields) -> None:
    path = _job_path(job_id)
    current = {}
    if path.is_file():
        try:
            current = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            current = {}
    current.update(fields)
    path.write_text(json.dumps(current))


def _read_status(job_id: str) -> dict | None:
    path = _job_path(job_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _cleanup_intermediate_files(root: Path) -> None:
    """Remove per-scene footage/audio/clip files once the final MP4 exists,
    so disk doesn't fill up across many large renders. Leaves output/ alone."""
    for name in ("footage", "audio", "scenes"):
        shutil.rmtree(root / name, ignore_errors=True)


def _run_job(job_id: str, raw_script: dict) -> None:
    _write_status(job_id, status="running", started_at=time.time())
    try:
        # Validate through the same schema check used everywhere else, by
        # round-tripping through a temp file (load_script reads from a path).
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(raw_script, f)
            temp_path = Path(f.name)
        try:
            script = load_script(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        output_path = process(script)
        _cleanup_intermediate_files(project_dir(script["project_id"]))
        _write_status(job_id, status="complete", output_path=str(output_path), finished_at=time.time())
    except (ValueError, GiphyError, PexelsError, TTSError, FFmpegError) as exc:
        logger.warning("Render job %s failed: %s", job_id, exc)
        _write_status(job_id, status="failed", error=str(exc), finished_at=time.time())
    except Exception as exc:  # noqa: BLE001 -- surface anything unexpected too
        logger.exception("Render job %s failed unexpectedly", job_id)
        _write_status(job_id, status="failed", error=f"Unexpected error: {exc}", finished_at=time.time())


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "render-worker"}


@app.post("/render")
def start_render(payload: RenderRequest, x_render_token: str | None = Header(default=None)):
    _check_token(x_render_token)
    job_id = uuid.uuid4().hex
    _write_status(job_id, status="queued", created_at=time.time())
    thread = threading.Thread(target=_run_job, args=(job_id, payload.script), daemon=True)
    thread.start()
    return {"job_id": job_id}


@app.get("/render/{job_id}")
def render_status(job_id: str, x_render_token: str | None = Header(default=None)):
    _check_token(x_render_token)
    data = _read_status(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return {"status": data.get("status"), "error": data.get("error")}


@app.get("/render/{job_id}/download")
def render_download(job_id: str, x_render_token: str | None = Header(default=None)):
    _check_token(x_render_token)
    data = _read_status(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    if data.get("status") != "complete":
        raise HTTPException(status_code=409, detail=f"Job status is {data.get('status')}, not complete")
    output_path = Path(data["output_path"])
    if not output_path.is_file():
        raise HTTPException(status_code=410, detail="Output file no longer available")
    return FileResponse(output_path, media_type="video/mp4", filename="empire_video.mp4")
