FROM python:3.11-slim AS dependencies
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.11-slim
WORKDIR /app
LABEL org.triad-bluff.protocol="1.0" org.triad-bluff.runtime="2" \
      org.triad-bluff.cpu="1" org.triad-bluff.ram-bytes="1073741824" \
      org.triad-bluff.scratch-bytes="1073741824" \
      org.triad-bluff.gpu="false" org.triad-bluff.gpu-bytes="0"
COPY --from=dependencies /app/.venv ./.venv
COPY src/ ./src/
COPY models/ ./models/
COPY submission.json ./
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 HOME=/tmp
USER 10000:10000
ENTRYPOINT ["python", "src/agent.py"]
