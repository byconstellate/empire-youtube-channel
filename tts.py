"""Local voice-cloning TTS using the open-source Chatterbox model."""

import os
import subprocess
import tempfile
import threading
from pathlib import Path


class TTSError(RuntimeError):
    """Raised when local voice generation fails."""


DEFAULT_REFERENCE_VOICE = Path(__file__).resolve().with_name("reference_voice.wav")
_model = None
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


def _load_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            import torch
            thread_count = int(os.getenv("TORCH_NUM_THREADS", "1"))
            torch.set_num_threads(thread_count)
            try:
                torch.set_num_interop_threads(thread_count)
            except RuntimeError:
                pass
            from chatterbox.tts_turbo import ChatterboxTurboTTS

            device = "cuda" if torch.cuda.is_available() else "cpu"
            # Nano keeps local CPU deployments practical while retaining zero-shot cloning.
            _model = ChatterboxTurboTTS.from_pretrained(device=device, nano=True)
        except Exception as exc:
            raise TTSError(f"Could not load the local Chatterbox voice model: {exc}") from exc
    return _model


def generate_voice(text: str, output_path: Path, language: str = "en") -> None:
    """Create one MP3 using the bundled reference voice and local Chatterbox.

    The language argument remains part of the public interface for compatibility
    with the existing renderer; Chatterbox Turbo Nano is the English voice model.
    """
    del language
    reference = _reference_voice_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import torchaudio as ta

        model = _load_model()
        waveform = model.generate(text, audio_prompt_path=str(reference))
        if waveform.ndim == 1:
            waveform = waveform.unsqueeze(0)
        with tempfile.TemporaryDirectory(prefix="empire_tts_") as temp_dir:
            wav_path = Path(temp_dir) / "voice.wav"
            ta.save(str(wav_path), waveform.detach().cpu(), model.sr)
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
