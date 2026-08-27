"""Pexels search, approval, and download helpers."""

import os
import sys
from pathlib import Path
from typing import Any

import requests


class PexelsError(RuntimeError):
    pass


def search_videos(api_key: str, query: str, per_page: int = 10) -> list[dict[str, Any]]:
    if not api_key:
        raise PexelsError("PEXELS_API_KEY is missing. Add it to your environment or .env file.")

    try:
        response = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": api_key},
            params={"query": query, "per_page": per_page, "orientation": "portrait"},
            timeout=30,
        )
        response.raise_for_status()
        videos = response.json().get("videos", [])
    except requests.RequestException as exc:
        raise PexelsError(f"Pexels search failed: {exc}") from exc

    if not videos:
        raise PexelsError(f'Pexels returned no videos for "{query}".')
    return videos


def choose_video(candidates: list[dict[str, Any]], scene_id: str) -> dict[str, Any]:
    """Choose footage interactively locally, or automatically on Render."""
    if (os.getenv("AUTO_APPROVE_FOOTAGE", "").lower() in {"1", "true", "yes"} or not sys.stdin.isatty()):
        return candidates[0]

    for index, video in enumerate(candidates, start=1):
        files = video.get("video_files", [])
        preview = next((item for item in files if item.get("width", 0) > item.get("height", 0)), None)
        preview_url = preview.get("link") if preview else video.get("image", "")
        print(f"\nScene {scene_id} candidate {index}/{len(candidates)}")
        print(f"Preview: {preview_url}")
        print("Press Enter to approve, or type 'r' to reject.")
        if input("> ").strip().lower() != "r":
            return video
    raise PexelsError(f"No footage approved for scene {scene_id}.")


def best_download_url(video: dict[str, Any]) -> str:
    files = video.get("video_files", [])
    if not files:
        raise PexelsError("The approved Pexels video has no downloadable files.")
    portrait = [item for item in files if item.get("width", 0) <= item.get("height", 0)]
    choices = portrait or files
    max_width = int(os.getenv("MAX_SOURCE_WIDTH", "1080"))
    bounded = [item for item in choices if 0 < item.get("width", 0) <= max_width]
    selected = max(bounded, key=lambda item: item.get("width", 0)) if bounded else min(choices, key=lambda item: item.get("width", 0))
    return selected["link"]


def download_video(video: dict[str, Any], output_path: Path) -> None:
    try:
        with requests.get(best_download_url(video), timeout=120, stream=True) as response:
            response.raise_for_status()
            with output_path.open("wb") as output_file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output_file.write(chunk)
    except (requests.RequestException, OSError, KeyError) as exc:
        raise PexelsError(f"Video download failed: {exc}") from exc
