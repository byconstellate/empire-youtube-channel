"""YouTube clip download via yt-dlp: fetch just a specific time range from a
video the user picked and trimmed in the app, rather than the whole thing."""

import re
import subprocess
from pathlib import Path

import yt_dlp

_VIDEO_ID_PATTERN = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)


class YouTubeError(RuntimeError):
    pass


def extract_video_id(url: str) -> str:
    """Pull the 11-character video ID out of a YouTube URL, handling the
    common URL shapes (watch, shorts, youtu.be short links, embed)."""
    match = _VIDEO_ID_PATTERN.search(url)
    if not match:
        raise YouTubeError(f"Could not find a YouTube video ID in: {url}")
    return match.group(1)


def _has_valid_video_stream(path: Path) -> bool:
    """True only if ffprobe can find an actual, decodable video stream in
    path -- not just that the file exists and is non-empty. A file can be a
    real, non-zero-byte file (e.g. an audio-only download, a partial merge,
    or an error page yt-dlp happened to save) while still having no video
    stream at all; encoding would only fail on that much later, with a
    confusing ffmpeg error ("Stream map '' matches no streams") that gives
    no hint the actual problem was a bad download."""
    try:
        completed = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return completed.returncode == 0 and completed.stdout.strip() == "video"
    except (subprocess.TimeoutExpired, OSError):
        return False


def download_youtube_clip(video_id: str, start_seconds: float, end_seconds: float, output_path: Path) -> None:
    """Download just the [start_seconds, end_seconds) portion of a YouTube
    video to output_path (as .mp4), using yt-dlp's range-download support so
    the whole source video is never fetched for what might be a short clip.
    """
    if start_seconds < 0:
        raise YouTubeError(f"start_seconds ({start_seconds}) cannot be negative.")
    if end_seconds <= start_seconds:
        raise YouTubeError(f"end_seconds ({end_seconds}) must be after start_seconds ({start_seconds}).")

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "download_ranges": yt_dlp.utils.download_range_func(None, [(start_seconds, end_seconds)]),
        "force_keyframes_at_cuts": True,
        "merge_output_format": "mp4",
        "outtmpl": str(output_path),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "overwrites": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        raise YouTubeError(
            f"Failed to download YouTube clip {video_id} [{start_seconds}-{end_seconds}]: {exc}"
        ) from exc

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise YouTubeError(
            f"yt-dlp reported success but no valid output file was found for {video_id} at {output_path}."
        )

    if not _has_valid_video_stream(output_path):
        output_path.unlink(missing_ok=True)
        raise YouTubeError(
            f"yt-dlp produced a file for {video_id} [{start_seconds}-{end_seconds}] but it has no "
            f"readable video stream -- the download likely failed partway through or picked an "
            f"audio-only format. Try this clip again, or pick a different time range."
        )
