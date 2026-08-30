"""Voice generation through a remote or local Kyutai Pocket TTS model."""

import os
import subprocess
import tempfile
import threading
from pathlib import Path


class TTSError(RuntimeError):
    """Raised when voice generation fails."""


DEFAULT_REFERENCE_VOICE = Path(__file__).resolve().with_name("reference_voice.wav")
_model = None
_voice_state = None
_model_lock = threading.Lock()
_chatterbox_model = None
_chatterbox_model_lock = threading.Lock()


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
    """Load Pocket TTS and the cloned voice state once for local mode."""
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
            _model = TTSModel.load_model(quantize=True)
            _voice_state = _model.get_state_for_audio_prompt(str(reference))
        except Exception as exc:
            raise TTSError(f"Could not load the local Pocket TTS voice model: {exc}") from exc
    return _model, _voice_state


def _load_chatterbox_model():
    global _chatterbox_model
    if _chatterbox_model is not None:
        return _chatterbox_model
    with _chatterbox_model_lock:
        if _chatterbox_model is not None:
            return _chatterbox_model
        try:
            import torch
            from chatterbox.tts_turbo import ChatterboxTurboTTS

            device = os.getenv("CHATTERBOX_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
            _chatterbox_model = ChatterboxTurboTTS.from_pretrained(device=device, nano=True)
        except Exception as exc:
            raise TTSError(f"Could not load the Chatterbox voice model: {exc}") from exc
    return _chatterbox_model


def _generate_chatterbox_voice(text: str, output_path: Path) -> None:
    reference = _reference_voice_path()
    try:
        import torchaudio as ta

        model = _load_chatterbox_model()
        waveform = model.generate(text, audio_prompt_path=str(reference))
        if waveform.ndim == 1:
            waveform = waveform.unsqueeze(0)
        with tempfile.TemporaryDirectory(prefix="empire_chatterbox_") as temp_dir:
            wav_path = Path(temp_dir) / "voice.wav"
            ta.save(str(wav_path), waveform.detach().cpu(), model.sr)
            completed = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "2", str(output_path)],
                check=False, capture_output=True, text=True,
            )
            if completed.returncode:
                raise TTSError(completed.stderr.strip() or "ffmpeg could not encode the Chatterbox audio as MP3.")
    except TTSError:
        raise
    except Exception as exc:
        raise TTSError(f"Chatterbox voice generation failed: {exc}") from exc

def _generate_remote_chatterbox_voice(text: str, output_path: Path) -> None:
    service_url = os.getenv("TTS_SERVICE_URL", "").strip().rstrip("/")
    service_token = os.getenv("TTS_SERVICE_TOKEN", "").strip()
    if not service_url or not service_token:
        raise TTSError("TTS_SERVICE_URL and TTS_SERVICE_TOKEN are required for remote Chatterbox TTS.")
    try:
        import requests

        response = requests.post(
            f"{service_url}/synthesize",
            headers={"X-TTS-Token": service_token},
            json={"text": text},
            timeout=300,
        )
        response.raise_for_status()
        if not response.content:
            raise TTSError("Remote Chatterbox returned an empty audio response.")
        with tempfile.TemporaryDirectory(prefix="empire_remote_chatterbox_") as temp_dir:
            wav_path = Path(temp_dir) / "voice.wav"
            wav_path.write_bytes(response.content)
            completed = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "2", str(output_path)],
                check=False, capture_output=True, text=True,
            )
            if completed.returncode:
                raise TTSError(completed.stderr.strip() or "ffmpeg could not encode remote Chatterbox audio as MP3.")
    except TTSError:
        raise
    except requests.RequestException as exc:
        raise TTSError(f"Remote Chatterbox request failed: {exc}") from exc
    except Exception as exc:
        raise TTSError(f"Remote Chatterbox generation failed: {exc}") from exc

def _generate_local_pocket_voice(text: str, output_path: Path) -> None:
    try:
        import scipy.io.wavfile

        model, voice_state = _load_model_and_voice()
        audio = model.generate_audio(voice_state, text)
        with tempfile.TemporaryDirectory(prefix="empire_tts_") as temp_dir:
            wav_path = Path(temp_dir) / "voice.wav"
            scipy.io.wavfile.write(str(wav_path), model.sample_rate, audio.detach().cpu().numpy())
            completed = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "2", str(output_path)],
                check=False, capture_output=True, text=True,
            )
            if completed.returncode:
                raise TTSError(completed.stderr.strip() or "ffmpeg could not encode the generated voice as MP3.")
    except TTSError:
        raise
    except Exception as exc:
        raise TTSError(f"Local Pocket TTS generation failed: {exc}") from exc


def _generate_remote_pocket_voice(text: str, output_path: Path) -> None:
    """Ask the Compute Engine Pocket service for WAV audio, then make the MP3 locally."""
    service_url = os.getenv("TTS_SERVICE_URL", "").strip().rstrip("/")
    service_token = os.getenv("TTS_SERVICE_TOKEN", "").strip()
    if not service_url or not service_token:
        raise TTSError("TTS_SERVICE_URL and TTS_SERVICE_TOKEN are required for remote Pocket TTS.")
    try:
        import requests

        response = requests.post(
            f"{service_url}/synthesize",
            headers={"X-TTS-Token": service_token},
            json={"text": text},
            timeout=180,
        )
        response.raise_for_status()
        if not response.content:
            raise TTSError("Remote Pocket TTS returned an empty audio response.")
        with tempfile.TemporaryDirectory(prefix="empire_remote_tts_") as temp_dir:
            wav_path = Path(temp_dir) / "voice.wav"
            wav_path.write_bytes(response.content)
            completed = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "2", str(output_path)],
                check=False, capture_output=True, text=True,
            )
            if completed.returncode:
                raise TTSError(completed.stderr.strip() or "ffmpeg could not encode remote Pocket audio as MP3.")
    except TTSError:
        raise
    except requests.RequestException as exc:
        raise TTSError(f"Remote Pocket TTS request failed: {exc}") from exc
    except Exception as exc:
        raise TTSError(f"Remote Pocket TTS generation failed: {exc}") from exc


def unload_model() -> None:
    """Release any cached local model/voice state to free memory.

    Safe to call no matter which TTS_PROVIDER is active: for a remote
    provider there's nothing local to release, so this is effectively a
    no-op; for a local provider (Pocket or Chatterbox) this drops whichever
    one was actually loaded and forces garbage collection, so the model's
    memory is freed before the memory-heavy ffmpeg encoding pass begins.
    """
    global _model, _voice_state, _chatterbox_model
    with _model_lock:
        _model = None
        _voice_state = None
    with _chatterbox_model_lock:
        _chatterbox_model = None
    import gc

    gc.collect()


def generate_voice(text: str, output_path: Path, language: str = "en") -> None:
    """Generate narration with Chatterbox by default, or Pocket when selected."""
    del language
    output_path.parent.mkdir(parents=True, exist_ok=True)
    provider = os.getenv("TTS_PROVIDER", "chatterbox_remote").strip().lower()
    if provider in {"chatterbox_remote", "chatterbox_http"}:
        _generate_remote_chatterbox_voice(text, output_path)
    elif provider in {"chatterbox", "chatterbox_nano"}:
        _generate_chatterbox_voice(text, output_path)
    elif provider in {"pocket_remote", "remote"}:
        _generate_remote_pocket_voice(text, output_path)
    elif provider in {"pocket", "local"}:
        _generate_local_pocket_voice(text, output_path)
    else:
        raise TTSError(f"Unknown TTS_PROVIDER {provider!r}; use chatterbox_remote, chatterbox, pocket_remote, or pocket.")
