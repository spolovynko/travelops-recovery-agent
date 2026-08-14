FROM python:3.12.12-slim-bookworm AS runtime

ARG UV_VERSION=0.11.6
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN pip install --no-cache-dir "uv==${UV_VERSION}"
WORKDIR /app

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src
COPY reports ./reports
RUN uv sync --locked --no-dev --no-editable

RUN useradd --create-home --uid 10001 travelops && chown -R travelops:travelops /app
USER travelops
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["uvicorn", "travelops_recovery_agent.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
