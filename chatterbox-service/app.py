import io
import os
import secrets
import threading

import scipy.io.wavfile
from chatterbox.tts_turbo import ChatterboxTurboTTS
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="Empire Chatterbox TTS")
TOKEN = os.environ["TTS_TOKEN"]
VOICE_FILE = os.getenv("VOICE_FILE", "/app/reference_voice.wav")
DEVICE = os.getenv("CHATTERBOX_DEVICE", "cpu")
if not os.path.isfile(VOICE_FILE):
    raise RuntimeError(f"Reference voice file not found: {VOICE_FILE}")
MODEL = ChatterboxTurboTTS.from_pretrained(device=DEVICE, nano=True)
GENERATION_LOCK = threading.Lock()


class SynthesisRequest(BaseModel):
    text: str


@app.get("/healthz")
def healthz():
    return {"status": "ok", "model": "chatterbox-turbo-nano", "device": DEVICE}


@app.post("/synthesize")
def synthesize(request: SynthesisRequest, x_tts_token: str | None = Header(default=None)):
    if not x_tts_token or not secrets.compare_digest(x_tts_token, TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")
    text = request.text.strip()
    if not text or len(text) > 2000:
        raise HTTPException(status_code=400, detail="Text must contain 1–2000 characters")
    try:
        with GENERATION_LOCK:
            waveform = MODEL.generate(text, audio_prompt_path=VOICE_FILE)
            if waveform.ndim == 1:
                waveform = waveform.unsqueeze(0)
            output = io.BytesIO()
            scipy.io.wavfile.write(output, MODEL.sr, waveform.detach().cpu().numpy())
        return Response(content=output.getvalue(), media_type="audio/wav")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chatterbox generation failed: {exc}") from exc
