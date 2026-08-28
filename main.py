"""Empire video generator: script -> voice -> approved footage -> MP4."""

import argparse
import json
import sys
from pathlib import Path

from config import (
    GOOGLE_TTS_LANGUAGE,
    GIPHY_API_KEY,
    PEXELS_API_KEY,
    VIDEO_PAN_DIRECTION,
    VIDEO_PAN_REGION,
    VIDEO_TEXT_POSITION,
    project_dir,
)
from giphy import GiphyError, search_gifs
from pexels import PexelsError, choose_video, download_video, search_videos
from tts import TTSError, generate_voice
from video import FFmpegError, combine_scenes, create_text_scene, create_video_scene, ensure_ffmpeg


BACKGROUNDS = ["0xff00ff", "black", "white", "0xffffd6e9"]


def load_script(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read valid JSON from {path}: {exc}") from exc
    if not isinstance(data, dict) or not data.get("project_id") or not isinstance(data.get("scenes"), list):
        raise ValueError("Script must contain a project_id and a scenes array.")
    if not data["scenes"]:
        raise ValueError("Script must contain at least one scene.")

    previous_background = None
    for index, scene in enumerate(data["scenes"], start=1):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {index} must be an object.")
        required = {"scene_id", "text", "scene_type"}
        missing = required - scene.keys()
        if missing:
            raise ValueError(f"Scene {index} is missing: {', '.join(sorted(missing))}.")
        if not isinstance(scene["text"], str) or not scene["text"].strip():
            raise ValueError(f"Scene {index} text must be a non-empty string.")
        scene["duration_seconds"] = scene.get("duration_seconds", 5)
        try:
            duration = float(scene["duration_seconds"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Scene {index} duration must be a number.") from exc
        if duration <= 0 or duration > 60:
            raise ValueError(f"Scene {index} duration must be greater than 0 and no more than 60 seconds.")
        if scene["scene_type"] not in {"video", "text"}:
            raise ValueError(f'Scene {index} scene_type must be "video" or "text".')
        if scene["scene_type"] in {"video", "gif"} and not scene.get("search_query"):
            raise ValueError(f"{scene["scene_type"].title()} scene {index} requires search_query.")
        if scene["scene_type"] in {"video", "gif"} and scene.get("pan_region", VIDEO_PAN_REGION) not in {"top_50", "bottom_50"}:
            raise ValueError(f'Video scene {index} pan_region must be "top_50" or "bottom_50".')
        if scene["scene_type"] in {"video", "gif"} and scene.get("pan_direction", VIDEO_PAN_DIRECTION) not in {"top_to_bottom", "bottom_to_top"}:
            raise ValueError(f'Video scene {index} pan_direction must be "top_to_bottom" or "bottom_to_top".')
        if scene.get("text_position", VIDEO_TEXT_POSITION) not in {"middle", "bottom"}:
            raise ValueError(f'Scene {index} text_position must be "middle" or "bottom."')
        background = BACKGROUNDS[(index - 1) % len(BACKGROUNDS)]
        if background == previous_background:
            raise ValueError("Text scene backgrounds must not repeat consecutively.")
        previous_background = background
    return data


def process(script: dict) -> Path:
    ensure_ffmpeg()
    root = project_dir(script["project_id"])
    footage_dir, audio_dir, scenes_dir, output_dir = (
        root / "footage",
        root / "audio",
        root / "scenes",
        root / "output",
    )
    for directory in (footage_dir, audio_dir, scenes_dir, output_dir):
        directory.mkdir(parents=True, exist_ok=True)

    scene_paths: list[Path] = []
    for index, scene in enumerate(script["scenes"]):
        scene_id = str(scene["scene_id"])
        duration = float(scene["duration_seconds"])
        audio_path = audio_dir / f"scene_{scene_id}.mp3"
        scene_path = scenes_dir / f"scene_{scene_id}.mp4"
        print(f"\nGenerating voice for scene {scene_id}...")
        generate_voice(scene["text"], audio_path, GOOGLE_TTS_LANGUAGE)

        if scene["scene_type"] in {"video", "gif"}:
            selected_video = scene.get("selected_video")
            if isinstance(selected_video, dict) and selected_video.get("video_files"):
                print(f"Using approved footage for scene {scene_id}...")
                selected = selected_video
            else:
                print(f'Searching {"GIPHY" if scene["scene_type"] == "gif" else "Pexels"} for "{scene["search_query"]}"...')
                if scene["scene_type"] == "gif":
                    candidates = search_gifs(GIPHY_API_KEY, scene["search_query"])
                    if not candidates:
                        raise GiphyError(f'GIPHY returned no playable clips for "{scene["search_query"]}".')
                    selected = candidates[0]
                else:
                    selected = choose_video(search_videos(PEXELS_API_KEY, scene["search_query"]), scene_id)
            footage_path = footage_dir / f"scene_{scene_id}.mp4"
            download_video(selected, footage_path)
            create_video_scene(footage_path, audio_path, scene["text"], duration, scene_path, pan_direction=scene.get("pan_direction", VIDEO_PAN_DIRECTION), pan_region=scene.get("pan_region", VIDEO_PAN_REGION), text_position=scene.get("text_position", VIDEO_TEXT_POSITION))
        else:
            background = BACKGROUNDS[index % len(BACKGROUNDS)]
            create_text_scene(audio_path, scene["text"], duration, background, scene_path, text_position=scene.get("text_position", VIDEO_TEXT_POSITION))
        scene_paths.append(scene_path)

    final_path = output_dir / "final.mp4"
    combine_scenes(scene_paths, final_path, root)
    return final_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an Empire landscape YouTube video.")
    parser.add_argument("script", type=Path, help="Path to a JSON scene script.")
    args = parser.parse_args()
    try:
        script = load_script(args.script)
        final_path = process(script)
    except (ValueError, GiphyError, PexelsError, TTSError, FFmpegError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
    print(f"\nDone. Your video is ready at: {final_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())