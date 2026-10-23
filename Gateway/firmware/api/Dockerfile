# The api: login, roles, REST + SSE, web hosting. Build context: Gateway/firmware/api
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 MC_DATA_DIR=/data MC_PORT=8000 MC_WEB_DIR=/web
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install . && useradd --system --uid 10001 --no-create-home mc && mkdir /data /web && chown mc /data

USER mc
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/meta', timeout=4).status == 200 else 1)"
CMD ["mc-api", "run"]
