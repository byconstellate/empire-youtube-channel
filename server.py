"""Web wrapper for the Empire visual scene editor and renderer."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, request, send_file, stream_with_context

from config import GOOGLE_TTS_LANGUAGE, VIDEO_PAN_REGION
from giphy import GiphyError, search_gifs
from pexels import PexelsError, search_videos

app = Flask(__name__, static_folder="frontend", static_url_path="")
jobs = {}
jobs_lock = threading.Lock()
JOB_DIR = Path(os.getenv("RENDER_JOB_DIR", "projects/.render_jobs"))
JOB_DIR.mkdir(parents=True, exist_ok=True)

# When set, render-related requests are relayed to a persistent worker
# (e.g. running on a VM) instead of rendering locally via subprocess. This is
# what lets a long render survive without being killed by Render's own
# health-check-triggered restarts -- the worker has no such restart to fight.
# Left unset, everything falls back to the original local-subprocess behavior.
RENDER_WORKER_URL = os.getenv("RENDER_WORKER_URL", "").strip().rstrip("/")
RENDER_WORKER_TOKEN = os.getenv("RENDER_WORKER_TOKEN", "").strip()


def _worker_headers() -> dict:
    return {"X-Render-Token": RENDER_WORKER_TOKEN} if RENDER_WORKER_TOKEN else {}


# Best-effort permanent archive: every submitted script gets committed to
# GitHub the moment a render starts, independent of localStorage, the VM, or
# anything downstream. Opt-in -- disabled entirely unless both vars are set.
# Never allowed to block or fail an actual render: any error here is logged
# and swallowed, not raised.
GITHUB_ARCHIVE_TOKEN = os.getenv("GITHUB_ARCHIVE_TOKEN", "").strip()
GITHUB_ARCHIVE_REPO = os.getenv("GITHUB_ARCHIVE_REPO", "").strip()
GITHUB_ARCHIVE_PATH_PREFIX = os.getenv("GITHUB_ARCHIVE_PATH_PREFIX", "submitted-scripts").strip().strip("/")


def _archive_script_to_github(job_id: str, payload: dict) -> None:
    if not GITHUB_ARCHIVE_TOKEN or not GITHUB_ARCHIVE_REPO:
        return
    import base64
    from datetime import datetime, timezone

    try:
        project_id = str(payload.get("project_id", "unknown"))
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        path = f"{GITHUB_ARCHIVE_PATH_PREFIX}/{project_id}/{timestamp}_{job_id}.json"
        content = base64.b64encode(json.dumps(payload, indent=2).encode("utf-8")).decode("ascii")
        response = requests.put(
            f"https://api.github.com/repos/{GITHUB_ARCHIVE_REPO}/contents/{path}",
            headers={
                "Authorization": f"Bearer {GITHUB_ARCHIVE_TOKEN}",
                "Accept": "application/vnd.github+json",
            },
            json={
                "message": f"Archive submitted script: {project_id} ({job_id})",
                "content": content,
            },
            timeout=15,
        )
        if not response.ok:
            app.logger.warning("Script archive to GitHub failed (%s): %s", response.status_code, response.text[:300])
    except Exception as exc:  # noqa: BLE001 -- archival must never break a render
        app.logger.warning("Script archive to GitHub raised: %s", exc)


def _job_path(job_id: str) -> Path:
  return JOB_DIR / f"{job_id}.json"


def _persist_job(job_id: str, job: dict) -> None:
  JOB_DIR.mkdir(parents=True, exist_ok=True)
  target = _job_path(job_id)
  temporary = target.with_suffix(".tmp")
  temporary.write_text(json.dumps(job), encoding="utf-8")
  temporary.replace(target)


def set_job(job_id: str, **updates: str) -> dict:
  with jobs_lock:
      job = {**jobs.get(job_id, {}), **updates}
      jobs[job_id] = job
      _persist_job(job_id, job)
      return dict(job)


def get_job(job_id: str) -> dict | None:
  try:
      return json.loads(_job_path(job_id).read_text(encoding="utf-8"))
  except (FileNotFoundError, OSError, json.JSONDecodeError):
      with jobs_lock:
          job = jobs.get(job_id)
      return dict(job) if job else None


def recover_interrupted_jobs() -> None:
  for job_path in JOB_DIR.glob("*.json"):
      try:
          job = json.loads(job_path.read_text(encoding="utf-8"))
      except (OSError, json.JSONDecodeError):
          continue
      if job.get("status") in {"queued", "running"}:
          job["status"] = "failed"
          job["error"] = "Render worker restarted before this job completed. Start a new render."
          try:
              job_path.write_text(json.dumps(job), encoding="utf-8")
          except OSError:
              continue


recover_interrupted_jobs()


@app.after_request
def add_cors_headers(response):
  origin = request.headers.get("Origin")
  allowed_origin = os.getenv("FRONTEND_ORIGIN", "*")
  if allowed_origin == "*" or origin == allowed_origin:
      response.headers["Access-Control-Allow-Origin"] = origin or "*"
      response.headers["Vary"] = "Origin"
      response.headers["Access-Control-Allow-Headers"] = "Content-Type"
      response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
  return response


@app.route("/api/<path:api_path>", methods=["OPTIONS"])
def api_options(api_path: str):
  return ("", 204)

@app.get("/")
def index():
  return app.send_static_file("index.html")


@app.get("/healthz")
def healthz():
  return jsonify(status="ok")


def compact_video(video: dict, media_type: str) -> dict:
  files = video.get("video_files", [])
  preview = next((item for item in files if item.get("width", 0) <= item.get("height", 0)), None) or (files[0] if files else {})
  return {
      "id": video.get("id"),
      "image": video.get("image", ""),
      "duration": video.get("duration"),
      "preview_url": preview.get("link", ""),
      "video_files": files,
      "media_type": media_type,
      "provider": "giphy" if media_type == "gif" else "pexels",
  }


def run_render(job_id: str, payload: dict) -> None:
  set_job(job_id, status="running")
  script_path = None
  try:
      render_payload = dict(payload)
      language = render_payload.pop("language", GOOGLE_TTS_LANGUAGE)
      pan_region = render_payload.pop("pan_region", VIDEO_PAN_REGION)
      if language:
          os.environ["GOOGLE_TTS_LANGUAGE"] = str(language)
      if pan_region:
          os.environ["VIDEO_PAN_REGION"] = str(pan_region)
      with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as script_file:
          json.dump(render_payload, script_file)
          script_path = Path(script_file.name)
      # 5 days by default -- effectively unlimited for any realistic render,
      # but still bounded so a genuinely stuck process doesn't sit in
      # "running" forever with no way to know it's actually stuck. Set
      # RENDER_TIMEOUT_SECONDS to override.
      timeout_seconds = int(os.getenv("RENDER_TIMEOUT_SECONDS", str(5 * 24 * 60 * 60)))
      completed = subprocess.run([sys.executable, "main.py", str(script_path)], capture_output=True, text=True, timeout=timeout_seconds)
      if completed.returncode != 0:
          raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Render failed.")
      output = Path("projects") / str(render_payload["project_id"]) / "output" / "final.mp4"
      if not output.exists():
          raise RuntimeError("Renderer finished without producing an MP4.")
      set_job(job_id, status="complete", output=str(output))
  except Exception as exc:
      set_job(job_id, status="failed", error=str(exc))
  finally:
      if script_path:
          script_path.unlink(missing_ok=True)


@app.post("/api/preview")
def preview():
  payload = request.get_json(silent=True)
  if not isinstance(payload, dict) or not isinstance(payload.get("scenes"), list):
      return jsonify(error="Request must contain a scenes array."), 400
  previews = []
  try:
      for scene in payload["scenes"]:
          media_type = scene.get("media_type", scene.get("scene_type"))
          if media_type not in {"gif", "video"}:
              continue
          query = str(scene.get("search_query") or scene.get("text") or "").strip()
          if not query:
              continue
          queries = [query]
          if payload.get("expand"):
              queries.extend(f"{query} {suffix}" for suffix in ("pink", "woman", "aesthetic", "baddie"))
          candidates = []
          seen_ids = set()
          searcher = search_gifs if media_type == "gif" else search_videos
          api_key = os.getenv("GIPHY_API_KEY", "") if media_type == "gif" else os.getenv("PEXELS_API_KEY", "")
          for search_query in queries:
              found = searcher(api_key, search_query)
              for video in found:
                  video_id = video.get("id")
                  if video_id in seen_ids:
                      continue
                  seen_ids.add(video_id)
                  candidates.append(compact_video(video, media_type))
          previews.append({"scene_id": str(scene.get("scene_id")), "candidates": candidates})
  except (GiphyError, PexelsError) as exc:
      return jsonify(error=str(exc)), 422
  except Exception:
      return jsonify(error="Media preview search failed. Try again."), 422
  return jsonify(scenes=previews)


@app.post("/api/render")
def render():
  payload = request.get_json(silent=True)
  if not isinstance(payload, dict) or not payload.get("project_id") or not isinstance(payload.get("scenes"), list) or not payload["scenes"]:
      return jsonify(error="Request must contain a project_id and at least one scene."), 400

  # Archive first, before anything else can go wrong -- this is what actually
  # protects against losing a script, independent of whether the render
  # itself succeeds, the worker is reachable, or localStorage gets
  # overwritten. Runs in the background so a slow/unreachable GitHub never
  # delays the actual render.
  archive_id = uuid.uuid4().hex
  threading.Thread(target=_archive_script_to_github, args=(archive_id, payload), daemon=True).start()

  if RENDER_WORKER_URL:
      render_payload = dict(payload)
      language = render_payload.pop("language", None)
      try:
          response = requests.post(
              f"{RENDER_WORKER_URL}/render",
              json={"script": render_payload, "language": language},
              headers=_worker_headers(),
              timeout=30,
          )
      except requests.RequestException as exc:
          return jsonify(error=f"Could not reach the render worker: {exc}"), 502
      if not response.ok:
          return jsonify(error=response.text[:240] or "Render worker rejected the request."), 502
      job_id = response.json()["job_id"]
      return jsonify(job_id=job_id, status_url=f"/api/render/{job_id}", download_url=f"/api/render/{job_id}/download"), 202

  job_id = uuid.uuid4().hex
  set_job(job_id, status="queued")
  threading.Thread(target=run_render, args=(job_id, payload), daemon=True).start()
  return jsonify(job_id=job_id, status_url=f"/api/render/{job_id}", download_url=f"/api/render/{job_id}/download"), 202


@app.get("/api/render/<job_id>")
def render_status(job_id: str):
  if RENDER_WORKER_URL:
      try:
          response = requests.get(f"{RENDER_WORKER_URL}/render/{job_id}", headers=_worker_headers(), timeout=15)
      except requests.RequestException as exc:
          return jsonify(error=f"Could not reach the render worker: {exc}"), 502
      if response.status_code == 404:
          return jsonify(error="Render job not found."), 404
      if not response.ok:
          return jsonify(error=response.text[:240] or "Render worker error."), 502
      return jsonify(response.json())

  job = get_job(job_id)
  if not job:
      return jsonify(error="Render job not found."), 404
  return jsonify({key: value for key, value in job.items() if key != "output"})


@app.get("/api/render/<job_id>/download")
def render_download(job_id: str):
  if RENDER_WORKER_URL:
      try:
          response = requests.get(
              f"{RENDER_WORKER_URL}/render/{job_id}/download",
              headers=_worker_headers(),
              timeout=300,
              stream=True,
          )
      except requests.RequestException as exc:
          return jsonify(error=f"Could not reach the render worker: {exc}"), 502
      if response.status_code == 404:
          return jsonify(error="Render job not found."), 404
      if response.status_code == 409:
          return jsonify(error="Render is not complete yet."), 409
      if not response.ok:
          return jsonify(error="Render worker could not provide the file."), 502
      return Response(
          stream_with_context(response.iter_content(chunk_size=1024 * 1024)),
          mimetype="video/mp4",
          headers={"Content-Disposition": 'attachment; filename="empire_video.mp4"'},
      )

  job = get_job(job_id)
  if not job:
      return jsonify(error="Render job not found."), 404
  if job.get("status") != "complete":
      return jsonify(error="Render is not complete yet."), 409
  output = Path(job["output"])
  return send_file(output, mimetype="video/mp4", as_attachment=True, download_name=f"{output.parent.parent.name}-vertical.mp4")


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)

