# Cloud backend image (multi-arch). Build from the repository root:
#   docker build -f server/Dockerfile -t mc-server .
FROM python:3.13-slim AS build
WORKDIR /src
COPY core core
COPY server server
RUN pip install --no-cache-dir --prefix=/install ./core "./server[firebase]"

FROM python:3.13-slim
COPY --from=build /install /usr/local
# gid 1883 = mcbroker: the broker can read the generated psk/acl files (0640).
# /broker-files is created here so the shared volume gets this owner.
RUN groupadd -g 1883 mcbroker && useradd -u 10001 -g mcbroker -M -s /usr/sbin/nologin mc \
    && mkdir /broker-files && chown 10001:1883 /broker-files && chmod 2750 /broker-files
USER 10001:1883
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["mc-server", "serve", "--port", "8000"]
