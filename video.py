"""Straightforward ffmpeg wrappers for scenes and final concatenation."""

import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

from config import FONT_FILE, VIDEO_FPS, VIDEO_HEIGHT, VIDEO_PAN_DIRECTION, VIDEO_PAN_REGION, VIDEO_WIDTH


class FFmpegError(RuntimeError):
    pass


def ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise FFmpegError("ffmpeg is not installed or is not on PATH.")


def run_ffmpeg(args: list[str]) -> None:
    try:
        completed = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-threads", os.getenv("FFMPEG_THREADS", "1"), *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise FFmpegError(f"Could not start ffmpeg: {exc}") from exc
    if completed.returncode:
        raise FFmpegError(completed.stderr.strip() or "ffmpeg failed.")


def _font_args() -> list[str]:
    return [f"fontfile={FONT_FILE}"] if FONT_FILE else []


def wrap_caption(text: str) -> str:
    clean = " ".join(text.split())
    max_chars = max(20, VIDEO_WIDTH // 52)
    return "\n".join(
        textwrap.wrap(clean, width=max_chars, break_long_words=True, break_on_hyphens=False)
    )


def _caption_file(text: str) -> Path:
    handle, path = tempfile.mkstemp(prefix="empire_caption_", suffix=".txt")
    os.close(handle)
    caption_path = Path(path)
    caption_path.write_text(wrap_caption(text), encoding="utf-8")
    return caption_path


def caption_filter(caption_path: Path) -> str:
    path = caption_path.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:")
    font = ":".join(_font_args())
    prefix = f"{font}:" if font else ""
    return (
        f"drawtext={prefix}textfile='{path}':"
        "fontcolor=#ff00ff:fontsize=52:borderw=4:bordercolor=white:"
        "x=(w-text_w)/2:y=(h-text_h)/2:line_spacing=12"
    )


def footage_filter(
    text: str,
    duration: float,
    pan_direction: str,
    pan_region: str = VIDEO_PAN_REGION,
    caption_path: Path | None = None,
) -> str:
    """Scale footage and pan within the selected top or bottom half."""
    if pan_direction not in {"top_to_bottom", "bottom_to_top"}:
        raise FFmpegError(
            'VIDEO_PAN_DIRECTION must be "top_to_bottom" or "bottom_to_top".'
        )
    if pan_region not in {"top_50", "bottom_50"}:
        raise FFmpegError('VIDEO_PAN_REGION must be "top_50" or "bottom_50".')
    progress = f"t/{duration}" if pan_direction == "top_to_bottom" else f"(1-t/{duration})"
    if pan_region == "top_50":
        y_position = f"(ih-oh)*0.5*({progress})"
    else:
        y_position = f"(ih-oh)*(0.5+0.5*({progress}))"
    return (
        f"scale={VIDEO_WIDTH}:-2:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}:0:{y_position},"
        f"setsar=1,{caption_filter(caption_path)}"
    )


def create_video_scene(
    footage: Path,
    audio: Path,
    text: str,
    duration: float,
    output: Path,
    pan_direction: str = VIDEO_PAN_DIRECTION,
    pan_region: str = VIDEO_PAN_REGION,
) -> None:
    caption_path = _caption_file(text)
    try:
        video_filter = (
            footage_filter(text, duration, pan_direction, pan_region, caption_path)
        )
        run_ffmpeg(
            [
                "-stream_loop",
                "-1",
                "-i",
                str(footage),
                "-i",
                str(audio),
                "-t",
                str(duration),
                "-vf",
                video_filter,
                "-r",
                str(VIDEO_FPS),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-af",
                f"apad=whole_dur={duration}",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "28",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(output),
            ]
        )



    finally:
        caption_path.unlink(missing_ok=True)
def create_text_scene(audio: Path, text: str, duration: float, background: str, output: Path) -> None:
    caption_path = _caption_file(text)
    try:
        video_filter = caption_filter(caption_path)
        run_ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                f"color=c={background}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:r={VIDEO_FPS}",
                "-i",
                str(audio),
                "-t",
                str(duration),
                "-vf",
                video_filter,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-af",
                f"apad=whole_dur={duration}",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "28",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(output),
            ]
        )



    finally:
        caption_path.unlink(missing_ok=True)
def combine_scenes(scene_paths: list[Path], output: Path, work_dir: Path) -> None:
    concat_file = work_dir / "concat.txt"
    concat_file.write_text(
        "".join(f"file '{path.resolve().as_posix()}'\n" for path in scene_paths),
        encoding="utf-8",
    )
    run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output),
        ]
    )
