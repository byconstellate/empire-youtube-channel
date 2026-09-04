"""Empire video generator: script -> voice -> approved footage -> MP4."""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from youtube import YouTubeError, download_youtube_clip
from tts import TTSError, generate_voice, unload_model
from video import FFmpegError, combine_scenes, create_text_scene, create_video_scene, ensure_ffmpeg


BACKGROUNDS = ["0xff00ff", "black", "white", "0xffffd6e9"]
ALLOWED_COLORS = {"#000000", "#ffffff", "#00ff00", "#ff00ff"}
DEFAULT_TEXT_COLOR = "#ff00ff"
DEFAULT_OUTLINE_COLOR = "#ffffff"
# Only used when a scene has no explicit duration AND no audio to measure
# (audio_enabled: false with duration_seconds unset/0) -- there's no signal
# at all to derive a length from in that case, so this is a last resort.
FALLBACK_DURATION_SECONDS = 5.0


def _audio_duration_seconds(path: Path) -> float | None:
    """Measure a generated audio file's real duration via ffprobe. Returns
    None (rather than raising) if the file is missing or ffprobe fails, so a
    measurement problem degrades to the fallback/requested duration instead
    of failing the whole render."""
    try:
        completed = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(completed.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, OSError):
        return None


def _tts_friendly_text(text: str) -> str:
    """Convert ALL-CAPS words (2+ letters) to Title Case for the text sent to
    TTS, so e.g. "EMPIRE" is spoken as the word "Empire" instead of being
    spelled out letter-by-letter -- many TTS engines treat a fully
    uppercase word as an acronym/initialism by default. This only affects
    what gets synthesized as speech; the on-screen caption text (scene["text"]
    itself) is never touched, so visual emphasis from using caps is
    unaffected.
    """
    return re.sub(r"\b[A-Z]{2,}\b", lambda m: m.group(0).capitalize(), text)


def _is_reusable_media_file(path: Path) -> bool:
    """True if path exists and ffprobe can read a real duration from it --
    i.e. it's a complete, non-corrupt file safe to reuse rather than
    regenerate. Works for audio or video; ffprobe doesn't care which.

    This matters for resuming an interrupted render: a file that's zero
    bytes or truncated (e.g. the process was killed mid-write, as happens
    if the render-worker container restarts mid-job) must NOT be silently
    trusted as already-done -- that would leave a broken clip baked into
    the final video with no error ever raised.
    """
    if not path.is_file() or path.stat().st_size == 0:
        return False
    return _audio_duration_seconds(path) is not None


def _is_reusable_video_file(path: Path) -> bool:
    """Like _is_reusable_media_file, but specifically requires a real,
    decodable VIDEO stream -- not just any readable container-level
    duration. Used for footage and encoded scene clips specifically,
    both of which genuinely need a video stream to be usable at all.

    This distinction is what _is_reusable_media_file alone misses: a
    malformed download (e.g. an audio-only format yt-dlp picked, or a
    partial merge) can still have a readable container "duration" via
    ffprobe's generic format=duration query, even with zero video
    streams inside it -- passing the generic check while being
    completely useless for encoding. That gap let a broken YouTube
    clip download get resumed/reused as "already done" on a second
    attempt, reproducing the exact same ffmpeg failure ("Stream map ''
    matches no streams") instead of being correctly re-downloaded.
    """
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        completed = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return completed.returncode == 0 and completed.stdout.strip() == "video"
    except (subprocess.TimeoutExpired, OSError):
        return False


def scene_background(scene: dict, index: int) -> str:
    """The background this scene will actually render with.

    An explicit bg_color from the scene always wins; otherwise fall back
    to the historical auto-cycling behavior.
    """
    explicit = scene.get("bg_color")
    if explicit:
        return explicit
    return BACKGROUNDS[index % len(BACKGROUNDS)]


def load_script(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read valid JSON from {path}: {exc}") from exc
    if not isinstance(data, dict) or not data.get("project_id") or not isinstance(data.get("scenes"), list):
        raise ValueError("Script must contain a project_id and a scenes array.")
    if not data["scenes"]:
        raise ValueError("Script must contain at least one scene.")
    if "audio_enabled" in data and not isinstance(data["audio_enabled"], bool):
        raise ValueError("audio_enabled must be true or false.")

    for index, scene in enumerate(data["scenes"], start=1):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {index} must be an object.")
        required = {"scene_id", "text", "scene_type"}
        missing = required - scene.keys()
        if missing:
            raise ValueError(f"Scene {index} is missing: {', '.join(sorted(missing))}.")
        if not isinstance(scene["text"], str) or not scene["text"].strip():
            raise ValueError(f"Scene {index} text must be a non-empty string.")
        scene["duration_seconds"] = scene.get("duration_seconds", 0)
        try:
            duration = float(scene["duration_seconds"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Scene {index} duration must be a number.") from exc
        # 0 is a valid sentinel meaning "auto": at render time this becomes
        # whatever the generated narration actually takes, with no fixed
        # floor. Only reject genuinely invalid values.
        if duration < 0 or duration > 3600:
            raise ValueError(f"Scene {index} duration must be 0 (auto) or up to 3600 seconds (60 minutes).")
        if scene["scene_type"] not in {"video", "gif", "text"}:
            raise ValueError(f'Scene {index} scene_type must be "video", "gif", or "text".')
        if scene["scene_type"] in {"video", "gif"} and not scene.get("search_query"):
            raise ValueError(f'{scene["scene_type"].title()} scene {index} requires search_query.')
        if scene["scene_type"] in {"video", "gif"} and scene.get("pan_region", VIDEO_PAN_REGION) not in {"top_50", "bottom_50"}:
            raise ValueError(f'Video scene {index} pan_region must be "top_50" or "bottom_50".')
        if scene["scene_type"] in {"video", "gif"} and scene.get("pan_direction", VIDEO_PAN_DIRECTION) not in {"top_to_bottom", "bottom_to_top"}:
            raise ValueError(f'Video scene {index} pan_direction must be "top_to_bottom" or "bottom_to_top".')
        if scene["scene_type"] in {"video", "gif"} and scene.get("pan_mode", "pan") not in {"pan", "static_top", "static_middle", "static_bottom"}:
            raise ValueError(f'Video scene {index} pan_mode must be "pan", "static_top", "static_middle", or "static_bottom".')
        if "show_text" in scene and not isinstance(scene["show_text"], bool):
            raise ValueError(f'Scene {index} show_text must be true or false.')
        if scene.get("text_position", VIDEO_TEXT_POSITION) not in {"middle", "bottom"}:
            raise ValueError(f'Scene {index} text_position must be "middle" or "bottom."')
        if scene.get("text_color", DEFAULT_TEXT_COLOR) not in ALLOWED_COLORS:
            raise ValueError(f'Scene {index} text_color must be one of {sorted(ALLOWED_COLORS)}.')
        if scene.get("outline_color", DEFAULT_OUTLINE_COLOR) not in ALLOWED_COLORS:
            raise ValueError(f'Scene {index} outline_color must be one of {sorted(ALLOWED_COLORS)}.')
        if "bg_color" in scene and scene["bg_color"] and scene["bg_color"] not in ALLOWED_COLORS:
            raise ValueError(f'Scene {index} bg_color must be one of {sorted(ALLOWED_COLORS)}.')
    return data


def _render_scene(
    index: int,
    scene: dict,
    audio_paths: dict,
    audio_durations: dict,
    footage_dir: Path,
    scenes_dir: Path,
    on_footage_done=None,
    on_encoded_done=None,
) -> tuple[int, Path]:
    """Download footage (if needed) and encode one scene. Safe to call concurrently
    across scenes: each writes to its own scene_id-keyed paths, and audio_paths is
    only read here, never written (all narration was already generated beforehand).

    on_footage_done() is called once footage is downloaded (video/gif scenes only;
    never called for text scenes, which have no footage step). on_encoded_done() is
    called once the scene's clip is fully encoded (all scene types). Both callbacks
    must be safe to call from multiple threads at once.
    """
    scene_id = str(scene["scene_id"])
    requested_duration = float(scene["duration_seconds"])  # 0 means "auto"
    measured_duration = audio_durations.get(scene_id)
    if measured_duration is not None:
        # Never let a scene be shorter than its own narration -- a shorter
        # requested duration is overridden up to match; a longer one (an
        # intentional pause after the line finishes) is respected as-is.
        duration = max(requested_duration, measured_duration)
    else:
        # No narration to measure (audio disabled, or measurement failed):
        # fall back to whatever was requested, or a fixed default if that's
        # also unset, since a scene needs *some* positive length either way.
        duration = requested_duration or FALLBACK_DURATION_SECONDS
    audio_path = audio_paths[scene_id]
    scene_path = scenes_dir / f"scene_{scene_id}.mp4"
    text_color = scene.get("text_color", DEFAULT_TEXT_COLOR)
    outline_color = scene.get("outline_color", DEFAULT_OUTLINE_COLOR)

    if _is_reusable_video_file(scene_path):
        # Already fully encoded from an earlier, interrupted attempt at this
        # same project_id -- reuse it as-is rather than redoing the (often
        # much slower) footage download + encode work. Still report progress
        # for it so the counts reflect true total completion, not just work
        # done in this particular run.
        print(f"Reusing already-encoded scene {scene_id} (resuming)...")
        if scene["scene_type"] in {"video", "gif"} and on_footage_done is not None:
            on_footage_done()
        if on_encoded_done is not None:
            on_encoded_done()
        return index, scene_path

    if scene["scene_type"] in {"video", "gif"}:
        selected_video = scene.get("selected_video")
        footage_path = footage_dir / f"scene_{scene_id}.mp4"
        if _is_reusable_video_file(footage_path):
            print(f"Reusing already-downloaded footage for scene {scene_id} (resuming)...")
        elif isinstance(selected_video, dict) and selected_video.get("provider") == "youtube":
            print(f"Downloading YouTube clip for scene {scene_id}...")
            download_youtube_clip(
                selected_video["video_id"],
                selected_video["start_seconds"],
                selected_video["end_seconds"],
                footage_path,
            )
        elif isinstance(selected_video, dict) and selected_video.get("video_files"):
            print(f"Using approved footage for scene {scene_id}...")
            download_video(selected_video, footage_path)
        else:
            provider = "GIPHY" if scene["scene_type"] == "gif" else "Pexels"
            query = scene["search_query"]
            print(f'Searching {provider} for "{query}"...')
            if scene["scene_type"] == "gif":
                candidates = search_gifs(GIPHY_API_KEY, scene["search_query"])
                if not candidates:
                    raise GiphyError(f'GIPHY returned no playable clips for "{scene["search_query"]}".')
                selected = candidates[0]
            else:
                selected = choose_video(search_videos(PEXELS_API_KEY, scene["search_query"]), scene_id)
            download_video(selected, footage_path)
        if on_footage_done is not None:
            on_footage_done()
        create_video_scene(
            footage_path,
            audio_path,
            scene["text"],
            duration,
            scene_path,
            pan_direction=scene.get("pan_direction", VIDEO_PAN_DIRECTION),
            pan_region=scene.get("pan_region", VIDEO_PAN_REGION),
            pan_mode=scene.get("pan_mode", "pan"),
            text_position=scene.get("text_position", VIDEO_TEXT_POSITION),
            show_text=scene.get("show_text", True),
            text_color=text_color,
            outline_color=outline_color,
        )
    else:
        background = scene_background(scene, index)
        create_text_scene(
            audio_path,
            scene["text"],
            duration,
            background,
            scene_path,
            text_position=scene.get("text_position", VIDEO_TEXT_POSITION),
            text_color=text_color,
            outline_color=outline_color,
        )
    if on_encoded_done is not None:
        on_encoded_done()
    return index, scene_path


def process(script: dict, language: str | None = None, on_progress=None) -> Path:
    """Render a script to a final MP4.

    on_progress, if given, is called with a dict snapshot of progress counts
    whenever any count changes:
      {"audio_done": int, "audio_total": int,
       "footage_done": int, "footage_total": int,
       "encoded_done": int, "encoded_total": int}
    Called synchronously from whichever thread just made progress, so it must
    be cheap and thread-safe (e.g. writing a small status file under a lock).
    """
    ensure_ffmpeg()
    language = language or GOOGLE_TTS_LANGUAGE
    root = project_dir(script["project_id"])
    footage_dir, audio_dir, scenes_dir, output_dir = (
        root / "footage",
        root / "audio",
        root / "scenes",
        root / "output",
    )
    for directory in (footage_dir, audio_dir, scenes_dir, output_dir):
        directory.mkdir(parents=True, exist_ok=True)

    audio_enabled = script.get("audio_enabled", True)
    total_scenes = len(script["scenes"])
    footage_total = sum(1 for s in script["scenes"] if s["scene_type"] in {"video", "gif"})
    counts = {
        "audio_done": 0,
        "audio_total": total_scenes if audio_enabled else 0,
        "footage_done": 0,
        "footage_total": footage_total,
        "encoded_done": 0,
        "encoded_total": total_scenes,
    }
    counts_lock = threading.Lock()

    def _bump(key: str) -> None:
        if on_progress is None:
            return
        with counts_lock:
            counts[key] += 1
            snapshot = dict(counts)
        on_progress(snapshot)

    if on_progress is not None:
        on_progress(dict(counts))

    audio_paths: dict[str, Path | None] = {}
    audio_durations: dict[str, float] = {}
    if audio_enabled:
        for scene in script["scenes"]:
            scene_id = str(scene["scene_id"])
            audio_path = audio_dir / f"scene_{scene_id}.mp3"
            if _is_reusable_media_file(audio_path):
                print(f"Reusing existing narration for scene {scene_id} (resuming)...")
            else:
                print(f"\nGenerating voice for scene {scene_id}...")
                generate_voice(_tts_friendly_text(scene["text"]), audio_path, language)
            audio_paths[scene_id] = audio_path
            measured = _audio_duration_seconds(audio_path)
            if measured is not None:
                audio_durations[scene_id] = measured
            _bump("audio_done")

        print("\nReleasing the voice model before encoding video...")
        unload_model()
    else:
        print("\nAudio disabled — skipping voice generation.")
        for scene in script["scenes"]:
            audio_paths[str(scene["scene_id"])] = None

    # Footage download + ffmpeg encoding is independent per scene (each writes
    # its own scene_id-keyed files), so it's safe -- and, for large scripts,
    # much faster -- to run several scenes at once. Each ffmpeg call already
    # runs with -threads 1 (see video.py/Dockerfile), so one worker per CPU
    # core doesn't oversubscribe. Override with RENDER_WORKERS if needed.
    max_workers = max(1, int(os.getenv("RENDER_WORKERS", str(os.cpu_count() or 1))))
    results: dict[int, Path] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _render_scene,
                index,
                scene,
                audio_paths,
                audio_durations,
                footage_dir,
                scenes_dir,
                on_footage_done=(lambda: _bump("footage_done")) if on_progress else None,
                on_encoded_done=(lambda: _bump("encoded_done")) if on_progress else None,
            ): index
            for index, scene in enumerate(script["scenes"])
        }
        for future in as_completed(futures):
            index, scene_path = future.result()
            results[index] = scene_path
    scene_paths = [results[i] for i in range(len(script["scenes"]))]

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
