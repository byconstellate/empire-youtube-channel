"""Web wrapper for the Empire visual scene editor and renderer."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from config import GOOGLE_TTS_LANGUAGE
from pexels import search_videos

app = Flask(__name__, static_folder="frontend", static_url_path="")
jobs = {}
jobs_lock = threading.Lock()

@app.get("/")
def index():
  return app.send_static_file("index.html")


def compact_video(video: dict) -> dict:
  files = video.get("video_files", [])
  preview = next((item for item in files if item.get("width", 0) <= item.get("height", 0)), None) or (files[0] if files else {})
  return {
      "id": video.get("id"),
      "image": video.get("image", ""),
      "duration": video.get("duration"),
      "preview_url": preview.get("link", ""),
      "video_files": files,
  }


def run_render(job_id: str, payload: dict) -> None:
  script_path = None
  try:
      render_payload = dict(payload)
      language = render_payload.pop("language", GOOGLE_TTS_LANGUAGE)
      if language:
          os.environ["GOOGLE_TTS_LANGUAGE"] = str(language)
      with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as script_file:
          json.dump(render_payload, script_file)
          script_path = Path(script_file.name)
      completed = subprocess.run([sys.executable, "main.py", str(script_path)], capture_output=True, text=True)
      if completed.returncode != 0:
          raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Render failed.")
      output = Path("projects") / str(render_payload["project_id"]) / "output" / "final.mp4"
      if not output.exists():
          raise RuntimeError("Renderer finished without producing an MP4.")
      with jobs_lock:
          jobs[job_id] = {"status": "complete", "output": str(output)}
  except Exception as exc:
      with jobs_lock:
          jobs[job_id] = {"status": "failed", "error": str(exc)}
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
          if scene.get("media_type", scene.get("scene_type")) != "video":
              continue
          query = str(scene.get("search_query") or scene.get("text") or "").strip()
          if not query:
              continue
          queries = [query]
          if payload.get("expand"):
              queries.extend(f"{query} {suffix}" for suffix in ("pink", "woman", "aesthetic", "baddie"))
          candidates = []
          seen_ids = set()
          for search_query in queries:
              for video in search_videos(os.getenv("PEXELS_API_KEY", ""), search_query):
                  video_id = video.get("id")
                  if video_id in seen_ids:
                      continue
                  seen_ids.add(video_id)
                  candidates.append(compact_video(video))
          previews.append({"scene_id": str(scene.get("scene_id")), "candidates": candidates})
  except Exception as exc:
      return jsonify(error=str(exc)), 422
  return jsonify(scenes=previews)


@app.post("/api/render")
def render():
  payload = request.get_json(silent=True)
  if not isinstance(payload, dict) or not payload.get("project_id") or not isinstance(payload.get("scenes"), list) or not payload["scenes"]:
      return jsonify(error="Request must contain a project_id and at least one scene."), 400
  job_id = uuid.uuid4().hex
  with jobs_lock:
      jobs[job_id] = {"status": "queued"}
  threading.Thread(target=run_render, args=(job_id, payload), daemon=True).start()
  return jsonify(job_id=job_id, status_url=f"/api/render/{job_id}", download_url=f"/api/render/{job_id}/download"), 202


@app.get("/api/render/<job_id>")
def render_status(job_id: str):
  with jobs_lock:
      job = jobs.get(job_id)
  if not job:
      return jsonify(error="Render job not found."), 404
  return jsonify({key: value for key, value in job.items() if key != "output"})


@app.get("/api/render/<job_id>/download")
def render_download(job_id: str):
  with jobs_lock:
      job = jobs.get(job_id)
  if not job:
      return jsonify(error="Render job not found."), 404
  if job.get("status") != "complete":
      return jsonify(error="Render is not complete yet."), 409
  output = Path(job["output"])
  return send_file(output, mimetype="video/mp4", as_attachment=True, download_name=f"{output.parent.parent.name}-vertical.mp4")


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
