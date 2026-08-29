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
            import torch
            from pocket_tts import TTSModel

            thread_count = int(os.getenv("TORCH_NUM_THREADS", "1"))
            torch.set_num_threads(thread_count)
            try:
                torch.set_num_interop_threads(thread_count)
            except RuntimeError:
                pass

            reference = _reference_voice_path()
            # quantize=True applies dynamic int8 quantization to the transformer's
            # attention/FFN layers: ~48% less runtime memory with no measurable
            # quality loss, per Kyutai's own benchmarks. Worth it on a memory-capped
            # host like Render's free/entry instance types.
            _model = TTSModel.load_model(quantize=True)
            _voice_state = _model.get_state_for_audio_prompt(str(reference))
        except Exception as exc:
            raise TTSError(f"Could not load the local Pocket TTS voice model: {exc}") from exc
    return _model, _voice_state


def unload_model() -> None:
    """Release the cached model and voice state to free memory.

    Call this once all scenes' narration has been generated and before starting
    memory-heavy ffmpeg encoding, so the torch model's resident memory and the
    video encoder's memory never have to coexist at their peaks.
    """
    global _model, _voice_state
    with _model_lock:
        _model = None
        _voice_state = None
    import gc

    gc.collect()


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
