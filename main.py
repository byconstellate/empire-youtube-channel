"""Empire video generator: plain-language scene choices to a vertical MP4."""

    import argparse
    import json
    import sys
    from pathlib import Path
    from urllib.parse import urlparse

    import requests

    from config import GOOGLE_TTS_LANGUAGE, PEXELS_API_KEY, project_dir
    from pexels import PexelsError, choose_video, download_video, search_videos
    from tts import TTSError, generate_voice
    from video import FFmpegError, combine_scenes, create_gif_scene, create_icon_scene, create_previous_scene, create_text_scene, create_video_scene, ensure_ffmpeg

    BACKGROUNDS = ["0xffd7c7b8", "0xff203049", "0xffb7d8cf", "0xffe6bb70"]
    MEDIA_TYPES = {"video", "icon", "gif", "previous", "text"}


    def media_type_for(scene: dict) -> str:
      if scene.get("media_type"):
          return str(scene["media_type"]).lower()
      return "video" if scene.get("scene_type") == "video" else "text"


    def load_script(path: Path) -> dict:
      try:
          data = json.loads(path.read_text(encoding="utf-8"))
      except (OSError, json.JSONDecodeError) as exc:
          raise ValueError(f"Could not read valid JSON from {path}: {exc}") from exc
      if not isinstance(data, dict) or not data.get("project_id") or not isinstance(data.get("scenes"), list):
          raise ValueError("Script must contain a project_id and a scenes array.")
      if not data["scenes"]:
          raise ValueError("Script must contain at least one scene.")
      for index, scene in enumerate(data["scenes"], start=1):
          if not isinstance(scene, dict):
              raise ValueError(f"Scene {index} must be an object.")
          required = {"scene_id", "text", "duration_seconds"}
          missing = required - scene.keys()
          if missing:
              raise ValueError(f"Scene {index} is missing: {', '.join(sorted(missing))}.")
          if not isinstance(scene["text"], str) or not scene["text"].strip():
              raise ValueError(f"Scene {index} text must be a non-empty string.")
          try:
              duration = float(scene["duration_seconds"])
          except (TypeError, ValueError) as exc:
              raise ValueError(f"Scene {index} duration must be a number.") from exc
          if duration <= 0 or duration > 60:
              raise ValueError(f"Scene {index} duration must be greater than 0 and no more than 60 seconds.")
          selected_type = media_type_for(scene)
          if selected_type not in MEDIA_TYPES:
              raise ValueError(f"Scene {index} media_type must be one of: {', '.join(sorted(MEDIA_TYPES))}.")
      return data


    def download_asset(url: str, output_path: Path) -> None:
      parsed = urlparse(url)
      if parsed.scheme not in {"http", "https"}:
          raise ValueError("GIF URL must start with http:// or https://.")
      try:
          response = requests.get(url, timeout=120)
          response.raise_for_status()
          output_path.write_bytes(response.content)
      except (requests.RequestException, OSError) as exc:
          raise ValueError(f"Could not download GIF asset: {exc}") from exc


    def process(script: dict) -> Path:
      ensure_ffmpeg()
      root = project_dir(script["project_id"])
      footage_dir, audio_dir, scenes_dir, output_dir = (root / "footage", root / "audio", root / "scenes", root / "output")
      for directory in (footage_dir, audio_dir, scenes_dir, output_dir):
          directory.mkdir(parents=True, exist_ok=True)

      scene_paths: list[Path] = []
      previous_scene_path: Path | None = None
      for index, scene in enumerate(script["scenes"]):
          scene_id = str(scene["scene_id"])
          duration = float(scene["duration_seconds"])
          selected_type = media_type_for(scene)
          audio_path = audio_dir / f"scene_{scene_id}.mp3"
          scene_path = scenes_dir / f"scene_{scene_id}.mp4"
          print(f"\nGenerating voice for scene {scene_id}...")
          generate_voice(scene["text"], audio_path, script.get("language", GOOGLE_TTS_LANGUAGE))

          if selected_type == "video":
              query = scene.get("search_query") or scene["text"]
              print(f'Searching Pexels for "{query}"...')
              selected = scene.get("selected_video") or choose_video(search_videos(PEXELS_API_KEY, query), scene_id)
              footage_path = footage_dir / f"scene_{scene_id}.mp4"
              download_video(selected, footage_path)
              create_video_scene(footage_path, audio_path, scene["text"], duration, scene_path)
          elif selected_type == "icon":
              create_icon_scene(audio_path, scene["text"], duration, scene.get("icon", "✦"), BACKGROUNDS[index % len(BACKGROUNDS)], scene_path)
          elif selected_type == "gif":
              gif_url = scene.get("selected_gif") or scene.get("gif_url")
              if gif_url:
                  gif_path = footage_dir / f"scene_{scene_id}.gif"
                  download_asset(str(gif_url), gif_path)
                  create_gif_scene(gif_path, audio_path, scene["text"], duration, scene_path)
              else:
                  create_icon_scene(audio_path, scene["text"], duration, "✦", BACKGROUNDS[index % len(BACKGROUNDS)], scene_path)
          elif selected_type == "previous" and previous_scene_path:
              gif_path = None
              gif_url = scene.get("selected_gif") or scene.get("gif_url")
              if scene.get("overlay") == "gif" and gif_url:
                  gif_path = footage_dir / f"scene_{scene_id}.gif"
                  download_asset(str(gif_url), gif_path)
              create_previous_scene(previous_scene_path, audio_path, scene["text"], duration, scene.get("overlay", "text"), scene.get("icon", "✦"), gif_path, scene_path)
          else:
              create_text_scene(audio_path, scene["text"], duration, BACKGROUNDS[index % len(BACKGROUNDS)], scene_path)
          scene_paths.append(scene_path)
          previous_scene_path = scene_path

      final_path = output_dir / "final.mp4"
      combine_scenes(scene_paths, final_path, root)
      return final_path


    def main() -> int:
      parser = argparse.ArgumentParser(description="Create an Empire vertical video from a scene plan.")
      parser.add_argument("script", type=Path)
      args = parser.parse_args()
      try:
          final_path = process(load_script(args.script))
      except (ValueError, PexelsError, TTSError, FFmpegError) as exc:
          print(f"\nError: {exc}", file=sys.stderr)
          return 1
      print(f"\nDone. Your video is ready at: {final_path}")
      return 0


    if __name__ == "__main__":
      raise SystemExit(main())
    