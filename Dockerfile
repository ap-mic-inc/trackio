FROM node:24-slim AS frontend
WORKDIR /src/trackio/frontend
COPY trackio/frontend/package.json trackio/frontend/package-lock.json ./
RUN npm ci
COPY trackio/frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SKIP_FRONTEND_BUILD=1 \
    TRACKIO_DIR=/data \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860
WORKDIR /app
COPY pyproject.toml hatch_build.py README.md LICENSE MANIFEST.in ./
COPY trackio/ ./trackio/
COPY --from=frontend /src/trackio/frontend/dist ./trackio/frontend/dist
RUN pip install . && rm -rf /app/trackio
# Coolify passes the deployed commit as SOURCE_COMMIT; the image has no .git.
ARG SOURCE_COMMIT=""
ENV TRACKIO_GIT_REVISION=$SOURCE_COMMIT
VOLUME ["/data"]
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/version', timeout=4)"
CMD ["trackio", "show", "--host", "0.0.0.0"]
