"""FFmpeg wrappers for Empire video scenes."""

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
          completed = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=False, capture_output=True, text=True)
      except OSError as exc:
          raise FFmpegError(f"Could not start ffmpeg: {exc}") from exc
      if completed.returncode:
          raise FFmpegError(completed.stderr.strip() or "ffmpeg failed.")


    def _font_args() -> list[str]:
      return [f"fontfile={FONT_FILE}"] if FONT_FILE else []


    def _escape_drawtext(text: str) -> str:
      return text.replace("\", "\\").replace(":", "\:").replace("'", "\'").replace("%", "\%").replace(",", "\,").replace("[", "\[").replace("]", "\]")


    def drawtext_filter(text: str, fontsize: int = 64, y: str = "h*0.72", color: str = "white") -> str:
      font = ":".join(_font_args())
      prefix = f"{font}:" if font else ""
      return f"drawtext={prefix}text='{_escape_drawtext(text)}':fontcolor={color}:fontsize={fontsize}:borderw=3:bordercolor=black@0.35:x=(w-text_w)/2:y={y}:line_spacing=12"


    def icon_filter(icon: str) -> str:
      return drawtext_filter(icon or "✦", fontsize=120, y="h*0.2", color="0xffffd0")


    def crop_filter() -> str:
      return f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}"


    def create_video_scene(footage: Path, audio: Path, text: str, duration: float, output: Path) -> None:
      run_ffmpeg(["-stream_loop", "-1", "-i", str(footage), "-i", str(audio), "-t", str(duration), "-vf", crop_filter() + "," + drawtext_filter(text), "-r", str(VIDEO_FPS), "-map", "0:v:0", "-map", "1:a:0", "-af", f"apad=whole_dur={duration}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output)])


    def create_text_scene(audio: Path, text: str, duration: float, background: str, output: Path) -> None:
      run_ffmpeg(["-f", "lavfi", "-i", f"color=c={background}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:r={VIDEO_FPS}", "-i", str(audio), "-t", str(duration), "-vf", drawtext_filter(text), "-map", "0:v:0", "-map", "1:a:0", "-af", f"apad=whole_dur={duration}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output)])


    def create_icon_scene(audio: Path, text: str, duration: float, icon: str, background: str, output: Path) -> None:
      run_ffmpeg(["-f", "lavfi", "-i", f"color=c={background}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:r={VIDEO_FPS}", "-i", str(audio), "-t", str(duration), "-vf", icon_filter(icon) + "," + drawtext_filter(text), "-map", "0:v:0", "-map", "1:a:0", "-af", f"apad=whole_dur={duration}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output)])


    def create_gif_scene(gif_path: Path, audio: Path, text: str, duration: float, output: Path) -> None:
      run_ffmpeg(["-stream_loop", "-1", "-i", str(gif_path), "-i", str(audio), "-t", str(duration), "-vf", crop_filter() + "," + drawtext_filter(text), "-r", str(VIDEO_FPS), "-map", "0:v:0", "-map", "1:a:0", "-af", f"apad=whole_dur={duration}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output)])


    def create_previous_scene(previous: Path, audio: Path, text: str, duration: float, overlay: str, icon: str, gif_path: Path | None, output: Path) -> None:
      if gif_path:
          filter_complex = "[0:v]" + crop_filter() + "[bg];[2:v]format=rgba,scale=360:-1[gif];[bg][gif]overlay=W-w-60:80[base];[base]" + drawtext_filter(text) + "[out]"
          run_ffmpeg(["-stream_loop", "-1", "-i", str(previous), "-i", str(audio), "-stream_loop", "-1", "-i", str(gif_path), "-t", str(duration), "-filter_complex", filter_complex, "-map", "[out]", "-map", "1:a:0", "-af", f"apad=whole_dur={duration}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output)])
          return
      overlay_filter = icon_filter(icon) + "," if overlay == "icon" else ""
      run_ffmpeg(["-stream_loop", "-1", "-i", str(previous), "-i", str(audio), "-t", str(duration), "-vf", crop_filter() + "," + overlay_filter + drawtext_filter(text), "-r", str(VIDEO_FPS), "-map", "0:v:0", "-map", "1:a:0", "-af", f"apad=whole_dur={duration}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output)])


    def combine_scenes(scene_paths: list[Path], output: Path, work_dir: Path) -> None:
      concat_file = work_dir / "concat.txt"
      concat_file.write_text("".join(f"file '{path.resolve().as_posix()}'\n" for path in scene_paths), encoding="utf-8")
      run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output)])
    