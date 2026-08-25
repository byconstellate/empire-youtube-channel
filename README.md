# Empire Video Generator

A landscape YouTube video generator:

`JSON script → TTS → approved Pexels footage → captions → ffmpeg → 1920×1080 MP4`

## Run the web app

Install Python 3.10+, ffmpeg, and dependencies, then configure `PEXELS_API_KEY` in `.env`:

```bash
pip install -r requirements.txt
python server.py
```

Open http://localhost:5000. **Start render** now calls the Python renderer and downloads the finished horizontal MP4. The GitHub Pages preview is static and cannot run Python, ffmpeg, TTS, or Pexels; use the web app server for actual video creation.

## CLI

`python main.py script.json`

The default output is 1920×1080 landscape MP4. Override `VIDEO_WIDTH`, `VIDEO_HEIGHT`, and `VIDEO_FPS` with environment variables when needed. Finished videos are written to `projects/<project_id>/output/final.mp4`.

## Script format

Each script contains a `project_id` and ordered `scenes`. Video scenes also require `search_query`.

```json
{
  "project_id": "empire_test_001",
  "scenes": [
    {"scene_id": "1", "text": "Your message.", "duration_seconds": 5, "scene_type": "video", "search_query": "woman working laptop business"},
    {"scene_id": "2", "text": "Your close.", "duration_seconds": 5, "scene_type": "text"}
  ]
}
```
