"""Local voice-cloning TTS using Kyutai's Pocket TTS model."""

import os
import subprocess
import tempfile
import threading
from pathlib import Path


class TTSError(RuntimeError):
    """Raised when local voice generation fails."""


DEFAULT_REFERENCE_VOICE = Path(__file__).resolve().with_name("reference_voice.wav")
_model = None
_voice_state = None
_model_lock = threading.Lock()


def _reference_voice_path() -> Path:
    configured = os.getenv("REFERENCE_VOICE_FILE", "").strip()
    reference = Path(configured) if configured else DEFAULT_REFERENCE_VOICE
    if not reference.is_absolute():
        reference = Path(__file__).resolve().parent / reference
    if not reference.is_file():
        raise TTSError(
            f"Reference voice file not found: {reference}. "
            "Add reference_voice.wav or set REFERENCE_VOICE_FILE."
        )
    return reference


def _load_model_and_voice():
    """Load the Pocket TTS model and the cloned voice state once, then reuse them.

    Both operations are relatively slow, so we cache them process-wide instead of
    repeating the work on every render, per Pocket TTS's own recommendation.
    """
    global _model, _voice_state
    if _model is not None and _voice_state is not None:
        return _model, _voice_state
    with _model_lock:
        if _model is not None and _voice_state is not None:
            return _model, _voice_state
        try:
            from pocket_tts import TTSModel

            reference = _reference_voice_path()
            _model = TTSModel.load_model()
            _voice_state = _model.get_state_for_audio_prompt(str(reference))
        except Exception as exc:
            raise TTSError(f"Could not load the local Pocket TTS voice model: {exc}") from exc
    return _model, _voice_state


def generate_voice(text: str, output_path: Path, language: str = "en") -> None:
    """Create one MP3 using the bundled reference voice and local Pocket TTS.

    The language argument remains part of the public interface for compatibility
    with the existing renderer; Pocket TTS clones the voice from the reference
    audio rather than switching models per language.
    """
    del language
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import scipy.io.wavfile

        model, voice_state = _load_model_and_voice()
        audio = model.generate_audio(voice_state, text)
        with tempfile.TemporaryDirectory(prefix="empire_tts_") as temp_dir:
            wav_path = Path(temp_dir) / "voice.wav"
            scipy.io.wavfile.write(str(wav_path), model.sample_rate, audio.detach().cpu().numpy())
            completed = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(wav_path),
                    "-codec:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode:
                raise TTSError(completed.stderr.strip() or "ffmpeg could not encode the generated voice as MP3.")
    except TTSError:
        raise
    except Exception as exc:
        raise TTSError(f"Local voice generation failed: {exc}") from exc
