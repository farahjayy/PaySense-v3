# PaySense API. Serves the forecast and risk check from committed model artefacts: no training
# stack in the image (no torch, no pandas, no scikit-learn), which is what keeps it small enough
# for a 512 MB host (ADR D-15).
#
#   docker build -t paysense-api backend
#   docker run --rm -p 8000:8000 --env-file .env paysense-api
#
# Build context is backend/. Secrets come from the environment at run time, never from the image.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, so a code-only change reuses this layer.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-default-groups --no-install-project
COPY app ./app
RUN uv sync --frozen --no-default-groups

FROM python:3.12-slim
RUN useradd --system --uid 10001 --no-create-home paysense
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/app /app/app
COPY models /app/models
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MODEL_DIR=/app/models
USER paysense
EXPOSE 8000

# One worker: the login rate limiter keeps its state in the process. FORWARDED_ALLOW_IPS must name
# the platform's proxy addresses (a CIDR is accepted), never "*", or a client could forge its
# address and dodge the limit. --limit-concurrency sheds load with a 503 instead of exhausting memory.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-127.0.0.1}\" --limit-concurrency 40 --timeout-keep-alive 5"]
