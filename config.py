"""Small configuration layer for the Empire video generator."""

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


ROOT = Path(__file__).resolve().parent
PROJECTS_DIR = ROOT / "projects"

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
GOOGLE_TTS_LANGUAGE = os.getenv("GOOGLE_TTS_LANGUAGE", "en")

# Landscape output for YouTube: standard 1280x720 HD.
VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1280"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "720"))
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "24"))
VIDEO_PAN_DIRECTION = os.getenv("VIDEO_PAN_DIRECTION", "top_to_bottom").lower()
VIDEO_PAN_REGION = os.getenv("VIDEO_PAN_REGION", "top_50").lower()
VIDEO_TEXT_POSITION = os.getenv("VIDEO_TEXT_POSITION", "bottom").lower()
FONT_FILE = os.getenv("FONT_FILE", "")


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id