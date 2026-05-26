FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Download spaCy model for PII redaction (separate layer so it survives dep-only rebuilds)
RUN /app/.venv/bin/python -m spacy download en_core_web_sm

# Copy application code and migration config
COPY app/ ./app/
COPY alembic.ini ./

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
