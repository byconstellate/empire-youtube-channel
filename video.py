"""Straightforward ffmpeg wrappers for scenes and final concatenation."""

import shutil
import subprocess
from pathlib import Path

from config import FONT_FILE, VIDEO_FPS, VIDEO_HEIGHT, VIDEO_WIDTH


class FFmpegError(RuntimeError):
    pass


def ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise FFmpegError("ffmpeg is not installed or is not on PATH.")


def run_ffmpeg(args: list[str]) -> None:
    try:
        completed = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
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


def _escape_drawtext(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")


def caption_filter(text: str) -> str:
    font = ":".join(_font_args())
    prefix = f"{font}:" if font else ""
    return (
        f"drawtext={prefix}text='{_escape_drawtext(text)}':"
        "fontcolor=white:fontsize=64:borderw=4:bordercolor=black:"
        "x=(w-text_w)/2:y=h*0.72:line_spacing=12"
    )


def create_video_scene(footage: Path, audio: Path, text: str, duration: float, output: Path) -> None:
    video_filter = (
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},{caption_filter(text)}"
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
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(output),
        ]
    )


def create_text_scene(audio: Path, text: str, duration: float, background: str, output: Path) -> None:
    video_filter = caption_filter(text)
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
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(output),
        ]
    )


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