# API server image (multi-arch). Build from the repository root:
#   docker build -f api/Dockerfile -t mc-api .
FROM python:3.13-slim AS build
WORKDIR /src
COPY core core
COPY api api
RUN pip install --no-cache-dir --prefix=/install ./core "./api[firebase]"

FROM python:3.13-slim
COPY --from=build /install /usr/local
RUN useradd -u 10001 -M -s /usr/sbin/nologin mc
USER 10001
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["mc-api", "serve", "--port", "8000"]
