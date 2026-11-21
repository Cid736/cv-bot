FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home appuser
USER appuser
ENV PORT=5001
EXPOSE 5001
# One worker: sessions and caches live in process memory. Threads handle concurrency.
CMD ["sh", "-c", "exec gunicorn --workers 1 --threads 8 --timeout 90 --bind 0.0.0.0:${PORT} app:app"]
