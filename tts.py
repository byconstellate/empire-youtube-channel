"""Voice generation with a lightweight Google default and optional local cloning."""

import os
import subprocess
import tempfile
import threading
from pathlib import Path


class TTSError(RuntimeError):
    """Raised when voice generation fails."""


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


def _load_chatterbox():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            import torch
            from chatterbox.tts_turbo import ChatterboxTurboTTS

            device = "cuda" if torch.cuda.is_available() else "cpu"
            _model = ChatterboxTurboTTS.from_pretrained(device=device, nano=True)
        except Exception as exc:
            raise TTSError(
                "Could not load the optional Chatterbox voice model. "
                "Use TTS_PROVIDER=google on Render or install chatterbox-tts locally: "
                f"{exc}"
            ) from exc
    return _model


def _generate_google_voice(text: str, output_path: Path, language: str) -> None:
    try:
        from gtts import gTTS

        # gTTS uses regional accents through tld rather than en-uk/en-au language codes.
        language_code = {"en-uk": "en", "en-au": "en"}.get(language, language or "en")
        gTTS(text=text, lang=language_code, slow=False).save(str(output_path))
    except Exception as exc:
        raise TTSError(f"Google voice generation failed: {exc}") from exc


def _generate_chatterbox_voice(text: str, output_path: Path) -> None:
    reference = _reference_voice_path()
    try:
        import torchaudio as ta

        model = _load_chatterbox()
        waveform = model.generate(text, audio_prompt_path=str(reference))
        if waveform.ndim == 1:
            waveform = waveform.unsqueeze(0)
        with tempfile.TemporaryDirectory(prefix="empire_tts_") as temp_dir:
            wav_path = Path(temp_dir) / "voice.wav"
            ta.save(str(wav_path), waveform.detach().cpu(), model.sr)
            completed = subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "2",
                    str(output_path),
                ],
                check=False, capture_output=True, text=True,
            )
            if completed.returncode:
                raise TTSError(completed.stderr.strip() or "ffmpeg could not encode the generated voice as MP3.")
    except TTSError:
        raise
    except Exception as exc:
        raise TTSError(f"Local voice generation failed: {exc}") from exc


def generate_voice(text: str, output_path: Path, language: str = "en") -> None:
    """Create one MP3; Google gTTS is the memory-safe deployment default."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    provider = os.getenv("TTS_PROVIDER", "google").strip().lower()
    if provider in {"google", "gtts"}:
        _generate_google_voice(text, output_path, language)
    elif provider in {"chatterbox", "local"}:
        _generate_chatterbox_voice(text, output_path)
    else:
        raise TTSError(f"Unknown TTS_PROVIDER {provider!r}; use google or chatterbox.")
