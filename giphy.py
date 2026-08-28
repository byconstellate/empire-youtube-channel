"""GIPHY search helpers for the web scene editor."""

import re
from typing import Any

import requests


class GiphyError(RuntimeError):
    pass


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _video_file(images: dict) -> dict | None:
    for key in ("original", "fixed_width", "downsized_medium", "downsized_small"):
        image = images.get(key) or {}
        link = image.get("mp4")
        if link:
            return {
                "link": link,
                "width": _number(image.get("mp4_width") or image.get("width")),
                "height": _number(image.get("mp4_height") or image.get("height")),
                "file_type": "video/mp4",
            }
    return None


def _compact_query(query: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", query)
    return " ".join(words[:6])[:64].strip()


def _search(api_key: str, query: str, limit: int, retry_short: bool = True) -> list[dict]:
    try:
        response = requests.get(
            "https://api.giphy.com/v1/gifs/search",
            params={
                "api_key": api_key,
                "q": query,
                "limit": limit,
                "rating": "pg-13",
                "lang": "en",
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("data", [])
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 414 and retry_short:
            shorter = " ".join(query.split()[:3])
            if shorter and shorter != query:
                return _search(api_key, shorter, limit, retry_short=False)
        detail = f"HTTP {status}" if status else "a network error"
        raise GiphyError(f"GIPHY search failed ({detail}). Try a shorter search phrase.") from exc
    except requests.RequestException as exc:
        raise GiphyError("GIPHY search failed. Check the server connection and try again.") from exc
    except ValueError as exc:
        raise GiphyError("GIPHY returned an invalid response.") from exc


def search_gifs(api_key: str, query: str, limit: int = 12) -> list[dict]:
    if not api_key:
        raise GiphyError("GIPHY_API_KEY is missing. Add it to your server environment.")
    query = _compact_query(query.strip())
    if not query:
        raise GiphyError("GIPHY search needs a non-empty line of text.")

    gifs = _search(api_key, query, limit)
    candidates = []
    for gif in gifs:
        images = gif.get("images") or {}
        video_file = _video_file(images)
        if not video_file:
            continue
        original = images.get("original") or {}
        candidates.append({
            "id": gif.get("id"),
            "title": gif.get("title") or query,
            "image": original.get("url") or "",
            "duration": gif.get("import_datetime"),
            "preview_url": video_file["link"],
            "video_files": [video_file],
        })

    if not candidates:
        raise GiphyError(f'GIPHY returned no playable clips for "{query}".')
    return candidates
