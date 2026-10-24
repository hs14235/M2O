FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt requirements-transcription.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Optional local speech-to-text: faster-whisper and its audio library only, not the rest
# of requirements-ai.txt. Compose passes TRANSCRIPTION_ENABLED here.
ARG TRANSCRIPTION=false
RUN if [ "$TRANSCRIPTION" = "true" ]; then pip install --no-cache-dir -r requirements-transcription.txt; fi
RUN useradd --create-home --uid 10001 app     && mkdir -p /home/app/.cache/huggingface && chown -R app:app /home/app/.cache
COPY --chown=app:app app ./app
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app alembic.ini ./
USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]
