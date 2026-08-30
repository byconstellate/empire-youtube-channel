FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    TORCH_NUM_THREADS=2

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY chatterbox-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY chatterbox-service/app.py .
COPY reference_voice.wav .

ENV VOICE_FILE=/app/reference_voice.wav
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
