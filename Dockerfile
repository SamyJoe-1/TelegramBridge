FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8000

# TG_API_ID, TG_API_HASH, TG_SESSION_STRING, BRIDGE_API_KEY must be
# supplied at runtime (docker run -e ... or a compose/env file) —
# never baked into the image.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
