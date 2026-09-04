FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIDEO_WIDTH=1280 \
    VIDEO_HEIGHT=720 \
    VIDEO_FPS=24 \
    MAX_SOURCE_WIDTH=720 \
    FFMPEG_THREADS=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core fonts-noto-color-emoji nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY render-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The actual render pipeline, copied flat alongside render-worker/app.py so
# imports like `from main import process` resolve as plain same-directory
# imports -- no sys.path tricks needed.
COPY main.py config.py video.py tts.py pexels.py giphy.py youtube.py .
COPY render-worker/app.py .

EXPOSE 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
