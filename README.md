# Empire Video Generator

A tiny command-line prototype for turning a user-supplied scene script into a landscape YouTube MP4:

`JSON script → TTS → approved Pexels footage → captions → ffmpeg → MP4`

It supports video scenes and full-screen text scenes, processes scenes in order, and keeps the voice provider behind one small adapter so a configured custom or cloned voice can be used.

## Requirements

- Python 3.10+
- `ffmpeg` installed and available on your PATH
- A Pexels API key
- Internet access for Google’s gTTS voice service

Install ffmpeg:

- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt install ffmpeg`
- Windows: install from [ffmpeg.org](https://ffmpeg.org/download.html) and add it to PATH

## Install

```bash
cd empire-video-generator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add values to `.env`:

```text
PEXELS_API_KEY=your_pexels_key
```

The program reads environment variables. If your shell does not load `.env` automatically, export the values before running, or load them with your preferred dotenv workflow. Google voice generation does not need a TTS API key. Set `GOOGLE_TTS_LANGUAGE` to a supported language code such as `en`, `en-au`, `en-uk`, or `th`.

## Web studio workflow

The browser studio accepts a plain-text script with one line per scene. After loading it, work through the lines in order:

1. Choose **Text**, **GIF**, or **Video** for the current line.
2. GIF lines automatically search GIPHY; video lines automatically search Pexels using the line text.
3. Select a media result when needed, then choose **Next line**.
4. Export the completed lineup to MP4.

The web preview endpoint uses the server-side `GIPHY_API_KEY` environment variable. Add that secret to the deployment; never put it in the browser code. The command-line renderer remains compatible with the existing JSON format and can use Pexels as its fallback when no clip is selected.

## Script format

Pass a JSON file with a `project_id` and ordered `scenes`. Video scenes require `search_query`; text scenes do not.

```json
{
  "project_id": "empire_test_001",
  "scenes": [
    {
      "scene_id": "1",
      "text": "your business doesn't need another strategy.",
      "duration_seconds": 5,
      "scene_type": "video",
      "search_query": "woman working laptop business"
    },
    {
      "scene_id": "2",
      "text": "it needs you to actually pick one.",
      "duration_seconds": 5,
      "scene_type": "text"
    }
  ]
}
```

## Run

```bash
python main.py script.json
```

For each video scene, the CLI prints candidate footage URLs. Press Enter to approve the current candidate or type `r` to reject it and see the next one.

The finished video appears at:

```text
projects/<project_id>/output/final.mp4
```

The default format is 1920×1080 landscape MP4 for YouTube. Portrait Pexels footage is scaled until it fills the landscape canvas, then gently panned through vertically during the scene. Set `VIDEO_PAN_DIRECTION=top_to_bottom` or `VIDEO_PAN_DIRECTION=bottom_to_top` to choose the direction. Change `VIDEO_WIDTH`, `VIDEO_HEIGHT`, and `VIDEO_FPS` when needed.

Generated audio, downloaded footage, and finished videos are ignored by git.
