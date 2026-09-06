FROM python:3.12.10-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/constraints.txt /app/constraints.txt
COPY backend/osint_watch /app/osint_watch
RUN pip install --no-cache-dir -c constraints.txt . && useradd --uid 10001 --create-home watch
COPY config /app/config
USER watch
EXPOSE 8000
CMD ["uvicorn", "osint_watch.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
