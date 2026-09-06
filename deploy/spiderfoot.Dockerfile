FROM python:3.10.17-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git gcc libxml2-dev libxslt1-dev libssl-dev libffi-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/spiderfoot
# Upstream release tag: repeatable source, independent from the main application.
RUN git clone --depth 1 --branch v4.0 https://github.com/smicallef/spiderfoot.git . && sed -i 's/pyyaml>=5.4.1,<6/pyyaml==6.0.3/' requirements.txt && pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir fastapi==0.115.12 uvicorn==0.34.2
COPY deploy/spiderfoot_bridge.py /opt/spiderfoot/bridge.py
RUN useradd --uid 10001 --create-home watch && chown -R watch:watch /opt/spiderfoot
USER watch
CMD ["uvicorn", "bridge:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]
