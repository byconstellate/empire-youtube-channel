"""Small configuration layer for the Empire video generator."""

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


ROOT = Path(__file__).resolve().parent
PROJECTS_DIR = ROOT / "projects"

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
GOOGLE_TTS_LANGUAGE = os.getenv("GOOGLE_TTS_LANGUAGE", "en")

VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1080"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1920"))
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "30"))
FONT_FILE = os.getenv("FONT_FILE", "")


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id