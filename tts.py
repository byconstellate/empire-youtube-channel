"""Replaceable text-to-speech abstraction using Google Translate voices."""

from pathlib import Path

from gtts import gTTS


class TTSError(RuntimeError):
    """Raised when Google voice generation fails."""


def generate_voice(text: str, output_path: Path, language: str = "en") -> None:
    """Create one MP3 using a Google Translate voice.

    This uses gTTS, so no TTS API key or voice ID is needed. Change the
    language code through GOOGLE_TTS_LANGUAGE for a different Google voice
    language, such as th, en-au, or en-uk.
    """
    try:
        gTTS(text=text, lang=language, slow=False).save(str(output_path))
    except (OSError, ValueError, RuntimeError) as exc:
        raise TTSError(f"Google voice generation failed: {exc}") from exc