FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.5.20 /uv /usr/local/bin/uv

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Download spaCy model for PII redaction (separate layer so it survives dep-only rebuilds)
RUN /app/.venv/bin/python -m spacy download en_core_web_sm

# Copy application code, migration config, and entrypoint
COPY app/ ./app/
COPY alembic.ini migrate.py ./

EXPOSE 8000

# migrate.py reads DB URL from Vault, runs `alembic upgrade head`, then execs uvicorn
CMD ["/app/.venv/bin/python", "migrate.py"]
