FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY src ./src
RUN pip install --no-cache-dir -c requirements.lock . \
    && useradd --create-home --uid 10001 pcb \
    && mkdir -p /app/.runtime/objects \
    && chown -R pcb:pcb /app/.runtime
COPY alembic.ini ./
COPY migrations ./migrations
USER pcb
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "pcb_inspector.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
