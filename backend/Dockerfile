FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt requirements-ml.txt ./
RUN pip install -r requirements.txt \
 && pip install -r requirements-ml.txt

# Bake the embedding model into the image so the container never needs the network at runtime.
ARG EMBEDDER_MODEL=sentence-transformers/all-MiniLM-L6-v2
ENV HF_HOME=/opt/hf
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDER_MODEL}')"
ENV HF_HUB_OFFLINE=1

COPY . .
RUN useradd -m app && mkdir -p /data/uploads && chown -R app /data /app
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
