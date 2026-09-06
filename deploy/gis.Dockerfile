FROM geopython/pygeoapi:0.21.0
USER root
RUN pip install --no-cache-dir 'psycopg2-binary==2.9.10'
COPY deploy/pygeoapi.yml /pygeoapi/local.config.yml
