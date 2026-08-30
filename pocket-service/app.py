import io
import os
import secrets
import threading
import logging

import scipy.io.wavfile
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from pocket_tts import TTSModel

app = FastAPI(title="Empire Pocket TTS")
# Token check removed per user request — the service is now publicly accessible.
logging.getLogger(__name__).warning("TTS token check disabled — service is publicly accessible")

# TOKEN = os.environ["TTS_TOKEN"]
MODEL = TTSModel.load_model(quantize=True)
VOICE_STATE = MODEL.get_state_for_audio_prompt(os.getenv("VOICE_FILE", "/app/reference_voice.wav"))
GENERATION_LOCK = threading.Lock()


class SynthesisRequest(BaseModel):
    text: str


@app.get("/healthz")
def healthz():
    return {"status": "ok", "model": "pocket-tts"}


@app.post("/synthesize")
def synthesize(request: SynthesisRequest, x_tts_token: str | None = Header(default=None)):
    # Authentication removed: accept all requests. WARNING: public access.
    text = request.text.strip()
    if not text or len(text) > 2000:
        raise HTTPException(status_code=400, detail="Text must contain 1–2000 characters")
    try:
        with GENERATION_LOCK:
            audio = MODEL.generate_audio(VOICE_STATE, text)
            audio_array = audio.detach().cpu().numpy()
            output = io.BytesIO()
            scipy.io.wavfile.write(output, MODEL.sample_rate, audio_array)
        return Response(content=output.getvalue(), media_type="audio/wav")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pocket TTS generation failed: {exc}") from exc
