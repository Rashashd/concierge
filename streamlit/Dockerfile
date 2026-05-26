FROM python:3.12-slim
RUN pip install --no-cache-dir streamlit
WORKDIR /app
RUN printf 'import streamlit as st\nst.title("Concierge Admin")\n' > app.py
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
