FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn
WORKDIR /app
RUN printf 'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/healthz")\ndef health(): return {"status": "ok"}\n' > main.py
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
