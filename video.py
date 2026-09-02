"""Straightforward ffmpeg wrappers for scenes and final concatenation."""

import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

from config import FONT_FILE, VIDEO_FPS, VIDEO_HEIGHT, VIDEO_PAN_DIRECTION, VIDEO_PAN_REGION, VIDEO_TEXT_POSITION, VIDEO_WIDTH

DEFAULT_TEXT_COLOR = "#ff00ff"
DEFAULT_OUTLINE_COLOR = "#ffffff"
DEFAULT_BG_COLOR = "#000000"


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


def _caption_line_files(text: str) -> list[Path]:
    """One temp file per wrapped line, so each line can be centered on its own."""
    lines = wrap_caption(text).split("\n")
    paths = []
    for line in lines:
        handle, path = tempfile.mkstemp(prefix="empire_caption_line_", suffix=".txt")
        os.close(handle)
        line_path = Path(path)
        line_path.write_text(line, encoding="utf-8")
        paths.append(line_path)
    return paths


def caption_filter(
    caption_path: Path,
    text_position: str = VIDEO_TEXT_POSITION,
    text_color: str = DEFAULT_TEXT_COLOR,
    outline_color: str = DEFAULT_OUTLINE_COLOR,
) -> str:
    """Build one or more chained drawtext filters, each line independently centered.

    caption_path may point to a file containing multiple newline-separated
    lines (from _caption_file); it is re-split here so each line gets its
    own drawtext with x=(w-text_w)/2, since this ffmpeg build doesn't
    support drawtext's text_align option for multi-line textfiles.
    """
    if text_position not in {"middle", "bottom"}:
        raise FFmpegError('TEXT_POSITION must be "middle" or "bottom".')
    lines = caption_path.read_text(encoding="utf-8").split("\n")
    font = ":".join(_font_args())
    prefix = f"{font}:" if font else ""
    line_height = 52 + 12  # fontsize + line_spacing, matches previous single-block layout
    total_height = line_height * len(lines)
    if text_position == "middle":
        top = f"(h-{total_height})/2"
    else:
        top = f"h*0.72-({total_height}/2)"
    filters = []
    for index, line in enumerate(lines):
        handle, tmp_path = tempfile.mkstemp(prefix="empire_caption_line_", suffix=".txt")
        os.close(handle)
        line_path = Path(tmp_path)
        line_path.write_text(line, encoding="utf-8")
        escaped_path = line_path.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:")
        y_position = f"({top})+{index}*{line_height}"
        filters.append(
            f"drawtext={prefix}textfile='{escaped_path}':"
            f"fontcolor={text_color}:fontsize=52:borderw=4:bordercolor={outline_color}:"
            f"x=(w-text_w)/2:y={y_position}"
        )
    return ",".join(filters)


def footage_filter(
    text: str,
    duration: float,
    pan_direction: str,
    pan_region: str = VIDEO_PAN_REGION,
    caption_path: Path | None = None,
    text_position: str = VIDEO_TEXT_POSITION,
    text_color: str = DEFAULT_TEXT_COLOR,
    outline_color: str = DEFAULT_OUTLINE_COLOR,
    pan_mode: str = "pan",
) -> str:
    """Scale footage and either pan within the top/bottom half, or hold a
    static crop at a fixed top/middle/bottom position.

    Pass caption_path=None to skip the text overlay entirely (e.g. when the
    scene's show_text flag is off) while keeping the pan/crop effect.
    """
    if pan_mode == "pan":
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
    elif pan_mode == "static_top":
        y_position = "0"
    elif pan_mode == "static_middle":
        y_position = "(ih-oh)/2"
    elif pan_mode == "static_bottom":
        y_position = "(ih-oh)"
    else:
        raise FFmpegError(
            'pan_mode must be "pan", "static_top", "static_middle", or "static_bottom".'
        )
    base = (
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(iw-ow)/2:{y_position},"
        "setsar=1"
    )
    if caption_path is None:
        return base
    return f"{base},{caption_filter(caption_path, text_position, text_color, outline_color)}"


def _frame_quantized_duration(duration: float, fps: int = VIDEO_FPS) -> float:
    """The exact duration a video track will actually have once encoded at
    fps: a whole number of frames, so there's no such thing as a partial
    frame. Rounds to the NEAREST frame boundary (not floor), so on average
    this is only off from the requested duration by half a frame either
    way, rather than always shrinking it.

    This value must be used for BOTH the video cutoff and the audio padding
    target for a scene -- using the raw, un-quantized `duration` for audio
    while video silently quantizes down to the nearest frame is exactly
    what causes video to end up a fraction of a frame shorter than audio,
    scene after scene. Individually that's imperceptible (tens of
    milliseconds), but concatenated across hundreds of scenes with no
    re-sync in between, it accumulates linearly into seconds of real,
    audible drift.
    """
    frame_count = max(1, round(duration * fps))
    return frame_count / fps


def create_video_scene(
    footage: Path,
    audio: Path | None,
    text: str,
    duration: float,
    output: Path,
    pan_direction: str = VIDEO_PAN_DIRECTION,
    pan_region: str = VIDEO_PAN_REGION,
    text_position: str = VIDEO_TEXT_POSITION,
    show_text: bool = True,
    text_color: str = DEFAULT_TEXT_COLOR,
    outline_color: str = DEFAULT_OUTLINE_COLOR,
    pan_mode: str = "pan",
) -> None:
    caption_path = _caption_file(text) if show_text else None
    try:
        exact_duration = _frame_quantized_duration(duration)
        video_filter = (
            footage_filter(text, exact_duration, pan_direction, pan_region, caption_path, text_position, text_color, outline_color, pan_mode)
        )
        ffmpeg_args = ["-stream_loop", "-1", "-i", str(footage)]
        if audio is not None:
            ffmpeg_args.extend(["-i", str(audio)])
        ffmpeg_args.extend(
            [
                "-t",
                str(exact_duration),
                "-vf",
                video_filter,
                "-r",
                str(VIDEO_FPS),
                "-map",
                "0:v:0",
            ]
        )
        if audio is not None:
            ffmpeg_args.extend(
                [
                    "-map",
                    "1:a:0",
                    "-af",
                    f"apad=whole_dur={exact_duration},atrim=duration={exact_duration}",
                    "-c:a",
                    "aac",
                    "-shortest",
                ]
            )
        else:
            ffmpeg_args.append("-an")
        ffmpeg_args.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "28",
                "-pix_fmt",
                "yuv420p",
                str(output),
            ]
        )
        run_ffmpeg(ffmpeg_args)
    finally:
        if caption_path is not None:
            caption_path.unlink(missing_ok=True)


def create_text_scene(
    audio: Path | None,
    text: str,
    duration: float,
    background: str,
    output: Path,
    text_position: str = VIDEO_TEXT_POSITION,
    text_color: str = DEFAULT_TEXT_COLOR,
    outline_color: str = DEFAULT_OUTLINE_COLOR,
) -> None:
    caption_path = _caption_file(text)
    try:
        exact_duration = _frame_quantized_duration(duration)
        video_filter = caption_filter(caption_path, text_position, text_color, outline_color)
        ffmpeg_args = [
            "-f",
            "lavfi",
            "-i",
            f"color=c={background}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:r={VIDEO_FPS}",
        ]
        if audio is not None:
            ffmpeg_args.extend(["-i", str(audio)])
        ffmpeg_args.extend(["-t", str(exact_duration), "-vf", video_filter, "-map", "0:v:0"])
        if audio is not None:
            ffmpeg_args.extend(
                [
                    "-map",
                    "1:a:0",
                    "-af",
                    f"apad=whole_dur={exact_duration},atrim=duration={exact_duration}",
                    "-c:a",
                    "aac",
                    "-shortest",
                ]
            )
        else:
            ffmpeg_args.append("-an")
        ffmpeg_args.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "28",
                "-pix_fmt",
                "yuv420p",
                str(output),
            ]
        )
        run_ffmpeg(ffmpeg_args)
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
            "-c:v",
            "copy",
            # Video stays a fast stream copy (unaffected, and this is the
            # expensive part of the file). Audio is re-encoded as ONE
            # continuous stream instead of also being copied: AAC encodes in
            # fixed 1024-sample frames and pads the last partial frame of
            # EVERY independently-encoded scene with a little trailing
            # silence, regardless of how precisely the input was trimmed.
            # Individually that's a few tens of milliseconds -- harmless.
            # Copied verbatim across ~460 independently-encoded scenes with
            # no re-sync in between, it accumulates linearly into seconds of
            # real, audible drift by the end of a long video. Encoding audio
            # once, continuously, here removes those ~460 internal
            # boundaries entirely.
            "-c:a",
            "aac",
            str(output),
        ]
    )
