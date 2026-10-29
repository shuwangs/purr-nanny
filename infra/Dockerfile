FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY server ./server
COPY storage ./storage
COPY web ./web
COPY packages/cat-health-signals ./packages/cat-health-signals
RUN pip install --no-cache-dir ./packages/cat-health-signals . && useradd --uid 10001 --create-home catnanny && mkdir /data && chown catnanny /data
ENV CAT_NANNY_DB=/data/cat_nanny.sqlite3
USER catnanny
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "server.mcp.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
