"""Migrate-and-start: read DB URL from Vault, run Alembic, exec uvicorn."""
import os
import sys

sys.path.insert(0, "/app")

from alembic import command
from alembic.config import Config

from app.infra.vault import create_vault_client

vault = create_vault_client(
    addr=os.environ["VAULT_ADDR"],
    token=os.environ["VAULT_TOKEN"],
)

# alembic/env.py reads DATABASE_URL from the environment and converts +asyncpg → +psycopg2
os.environ["DATABASE_URL"] = vault.get_database_url()

cfg = Config("/app/alembic.ini")
command.upgrade(cfg, "head")

os.execv(
    "/app/.venv/bin/uvicorn",
    [
        "/app/.venv/bin/uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ],
)
