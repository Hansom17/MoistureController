# Hub agent image (multi-arch). Build from the repository root:
#   docker build -f hub/Dockerfile -t mc-hub-agent .
FROM python:3.13-slim AS build
WORKDIR /src
COPY core core
COPY hub hub
RUN pip install --no-cache-dir --prefix=/install ./core ./hub qrcode

FROM python:3.13-slim
COPY --from=build /install /usr/local
# gid 1883 = mcbroker: Mosquitto can read the psk and bridge files (0640).
RUN groupadd -g 1883 mcbroker && useradd -u 10001 -g mcbroker -M -s /usr/sbin/nologin mc \
    && mkdir /data && chown 10001:1883 /data && chmod 2750 /data
USER 10001:1883
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MC_HUB_DATA=/data
CMD ["mc-hub", "run"]
