FROM openvino/ubuntu22_runtime:2026.1.0

ARG APP_UID=1000
ARG APP_GID=1000

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/audio_analyzer

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg alsa-utils libsndfile1 python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt

RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install -r requirements.txt

COPY . .

# Ensure all relevant directories exist, are not empty, and are chowned
RUN mkdir -p /app/audio_analyzer/models/openvino \
    && mkdir -p /app/audio_analyzer/models/dummy \
    && mkdir -p /app/audio_analyzer/chunks/dummy \
    && mkdir -p /app/audio_analyzer/storage/dummy \
    && mkdir -p /app/audio_analyzer/.cache/dummy \
    && touch /app/audio_analyzer/models/.keep \
    && touch /app/audio_analyzer/models/openvino/.keep \
    && touch /app/audio_analyzer/chunks/.keep \
    && touch /app/audio_analyzer/storage/.keep \
    && touch /app/audio_analyzer/.cache/.keep \
    && chown -R ${APP_UID}:${APP_GID} /app/audio_analyzer

USER ${APP_UID}:${APP_GID}

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=5).read()"

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010"]