"""Straightforward ffmpeg wrappers for scenes and final concatenation."""

import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import (
    CAPTION_TEXT_FONT_FILE,
    EMOJI_FONT_FILE,
    FONT_FILE,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_PAN_DIRECTION,
    VIDEO_PAN_REGION,
    VIDEO_TEXT_POSITION,
    VIDEO_WIDTH,
)

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


def _fit_caption_block(line_count: int, text_position: str) -> tuple[int, int, float]:
    """Pick the largest fontsize (from a small fixed set, down from the
    default 52) whose resulting text block actually fits within the frame
    for this many wrapped lines and this position, instead of always using
    a fixed size regardless of line count -- long captions were running
    off the bottom of the frame at the original fixed fontsize.

    Returns (fontsize, line_height, top). top is the numeric y position (in
    pixels, since VIDEO_HEIGHT is a fixed constant here, not an ffmpeg
    runtime expression) of the first line's top edge -- callers needing an
    ffmpeg drawtext expression string format it themselves; callers
    rendering directly with PIL can use it as-is.
    """
    margin = 24
    max_fontsize = 52
    min_fontsize = 24
    fontsize = max_fontsize
    while fontsize > min_fontsize:
        line_height = fontsize + 12
        total_height = line_height * line_count
        if text_position == "middle":
            top_value = (VIDEO_HEIGHT - total_height) / 2
            fits = top_value >= margin
        else:
            top_value = VIDEO_HEIGHT * 0.72 - total_height / 2
            fits = (top_value + total_height) <= VIDEO_HEIGHT - margin and top_value >= margin
        if fits:
            break
        fontsize -= 4
    line_height = fontsize + 12
    total_height = line_height * line_count
    if text_position == "middle":
        top_value = (VIDEO_HEIGHT - total_height) / 2
    else:
        top_value = VIDEO_HEIGHT * 0.72 - total_height / 2
    return fontsize, line_height, top_value


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
    fontsize, line_height, top_value = _fit_caption_block(len(lines), text_position)
    top = f"{top_value}"
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
            f"fontcolor={text_color}:fontsize={fontsize}:borderw=4:bordercolor={outline_color}:"
            f"x=(w-text_w)/2:y={y_position}"
        )
    return ",".join(filters)


_EMOJI_RANGES = [
    (0x1F300, 0x1FAFF),  # misc pictographs, emoticons, transport, supplemental symbols
    (0x2600, 0x27BF),  # misc symbols, dingbats (e.g. sparkles)
    (0x2190, 0x21FF),  # arrows
    (0x2B00, 0x2BFF),  # misc symbols and arrows
    (0xFE00, 0xFE0F),  # variation selectors
    (0x1F1E6, 0x1F1FF),  # regional indicators (flag emoji)
]


def _is_emoji_char(ch: str) -> bool:
    cp = ord(ch)
    return any(start <= cp <= end for start, end in _EMOJI_RANGES)


def contains_emoji(text: str) -> bool:
    return any(_is_emoji_char(ch) for ch in text)


def _split_emoji_runs(text: str) -> list[tuple[str, bool]]:
    """Split text into consecutive runs of (segment, is_emoji), so a mixed
    line can be rendered with a normal text font for the text parts and a
    color emoji font for the emoji parts."""
    if not text:
        return []
    runs: list[tuple[str, bool]] = []
    current = text[0]
    current_is_emoji = _is_emoji_char(text[0])
    for ch in text[1:]:
        ch_is_emoji = _is_emoji_char(ch)
        if ch_is_emoji == current_is_emoji:
            current += ch
        else:
            runs.append((current, current_is_emoji))
            current, current_is_emoji = ch, ch_is_emoji
    runs.append((current, current_is_emoji))
    return runs


def _render_caption_line_image(
    line: str, fontsize: int, text_color: str, outline_color: str, outline_width: int = 4
) -> Image.Image:
    """Render one line as an RGBA image with a transparent background,
    mixing a normal text font for regular characters with a color emoji
    font for emoji characters -- ffmpeg's drawtext filter can do neither
    (it can't mix fonts within one call, and can't rasterize color/bitmap
    emoji glyphs at all, which is what shows up as an empty square)."""
    text_font = ImageFont.truetype(CAPTION_TEXT_FONT_FILE, size=fontsize)
    # Noto Color Emoji only ships in one fixed strike size; request exactly
    # that, then resize the rendered glyph to match the surrounding text.
    emoji_native_size = 109
    emoji_font = ImageFont.truetype(EMOJI_FONT_FILE, size=emoji_native_size)
    emoji_display_size = int(fontsize * 1.15)  # emoji read as slightly small next to text otherwise
    scale = emoji_display_size / emoji_native_size

    runs = _split_emoji_runs(line)
    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    total_width = 0
    for run_text, is_emoji in runs:
        if is_emoji:
            for ch in run_text:
                bbox = emoji_font.getbbox(ch)
                total_width += int((bbox[2] - bbox[0]) * scale) if bbox else emoji_display_size
        else:
            total_width += int(dummy_draw.textlength(run_text, font=text_font))

    height = int(fontsize * 1.5)
    pad = outline_width * 2
    img = Image.new("RGBA", (total_width + pad * 2, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    x = pad
    baseline_y = height // 2
    for run_text, is_emoji in runs:
        if is_emoji:
            for ch in run_text:
                glyph = Image.new("RGBA", (emoji_native_size, emoji_native_size), (0, 0, 0, 0))
                ImageDraw.Draw(glyph).text((0, 0), ch, font=emoji_font, embedded_color=True)
                resized = glyph.resize((emoji_display_size, emoji_display_size), Image.LANCZOS)
                img.paste(resized, (x, baseline_y - emoji_display_size // 2), resized)
                x += emoji_display_size
        else:
            draw.text(
                (x, baseline_y), run_text, font=text_font, fill=text_color,
                stroke_width=outline_width, stroke_fill=outline_color, anchor="lm",
            )
            x += int(draw.textlength(run_text, font=text_font))
    return img


def render_caption_overlay(
    lines: list[str], text_position: str, text_color: str, outline_color: str
) -> Path:
    """Render a full caption block (all lines, correctly positioned and
    sized to match _fit_caption_block) as one full-frame transparent PNG,
    for scenes whose text contains emoji. Overlaying this whole image at
    (0, 0) is simpler and safer than trying to mix ffmpeg drawtext (for
    plain lines) with per-line image overlays (for emoji lines) in the same
    filter graph -- all the positioning math stays here in Python instead.
    """
    fontsize, line_height, top = _fit_caption_block(len(lines), text_position)
    frame = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    for index, line in enumerate(lines):
        line_img = _render_caption_line_image(line, fontsize, text_color, outline_color)
        x = (VIDEO_WIDTH - line_img.width) // 2
        y = int(top + index * line_height - line_img.height / 2 + fontsize / 2)
        frame.paste(line_img, (x, y), line_img)
    handle, path = tempfile.mkstemp(prefix="empire_caption_overlay_", suffix=".png")
    os.close(handle)
    overlay_path = Path(path)
    frame.save(overlay_path)
    return overlay_path


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
    overlay_path: Path | None = None
    try:
        exact_duration = _frame_quantized_duration(duration)
        use_overlay = show_text and contains_emoji(text)
        if use_overlay:
            # drawtext can neither mix fonts nor rasterize color emoji glyphs
            # (that's what shows up as an empty square) -- render the whole
            # caption block as one transparent PNG instead and overlay it.
            lines = wrap_caption(text).split("\n")
            overlay_path = render_caption_overlay(lines, text_position, text_color, outline_color)
            base_filter = footage_filter(text, exact_duration, pan_direction, pan_region, None, text_position, text_color, outline_color, pan_mode)
            ffmpeg_args = ["-stream_loop", "-1", "-i", str(footage)]
            if audio is not None:
                ffmpeg_args.extend(["-i", str(audio)])
            overlay_input_index = 2 if audio is not None else 1
            ffmpeg_args.extend(["-i", str(overlay_path)])
            ffmpeg_args.extend(
                [
                    "-t",
                    str(exact_duration),
                    "-filter_complex",
                    f"[0:v]{base_filter}[bg];[bg][{overlay_input_index}:v]overlay=0:0[outv]",
                    "-r",
                    str(VIDEO_FPS),
                    "-map",
                    "[outv]",
                ]
            )
        else:
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
        if overlay_path is not None:
            overlay_path.unlink(missing_ok=True)


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
    overlay_path: Path | None = None
    try:
        exact_duration = _frame_quantized_duration(duration)
        use_overlay = contains_emoji(text)
        if use_overlay:
            lines = wrap_caption(text).split("\n")
            overlay_path = render_caption_overlay(lines, text_position, text_color, outline_color)
            ffmpeg_args = [
                "-f",
                "lavfi",
                "-i",
                f"color=c={background}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:r={VIDEO_FPS}",
            ]
            if audio is not None:
                ffmpeg_args.extend(["-i", str(audio)])
            overlay_input_index = 2 if audio is not None else 1
            ffmpeg_args.extend(["-i", str(overlay_path)])
            ffmpeg_args.extend(
                [
                    "-t",
                    str(exact_duration),
                    "-filter_complex",
                    f"[0:v][{overlay_input_index}:v]overlay=0:0[outv]",
                    "-map",
                    "[outv]",
                ]
            )
        else:
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
        if overlay_path is not None:
            overlay_path.unlink(missing_ok=True)


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
