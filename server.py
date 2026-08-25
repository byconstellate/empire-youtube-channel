"""Small web wrapper for the Empire video renderer."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from config import GOOGLE_TTS_LANGUAGE

app = Flask(__name__, static_folder="frontend", static_url_path="")

@app.get("/")
def index():
    return app.send_static_file("index.html")

@app.post("/api/render")
def render():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Request body must be a JSON script."), 400
    language = payload.pop("language", GOOGLE_TTS_LANGUAGE)
    if language:
        os.environ["GOOGLE_TTS_LANGUAGE"] = str(language)
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as script_file:
            json.dump(payload, script_file)
            script_path = Path(script_file.name)
        completed = subprocess.run([sys.executable, "main.py", str(script_path)], capture_output=True, text=True)
    finally:
        if "script_path" in locals():
            script_path.unlink(missing_ok=True)
    if completed.returncode != 0:
        return jsonify(error=completed.stderr.strip() or completed.stdout.strip() or "Render failed."), 422
    output = Path("projects") / str(payload["project_id"]) / "output" / "final.mp4"
    if not output.exists():
        return jsonify(error="Renderer finished without producing an MP4."), 500
    return send_file(output, mimetype="video/mp4", as_attachment=True, download_name=f"{payload['project_id']}-landscape.mp4")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
