# Image for the public, read-only MCP server (compose profile "public"). The local stand runs from .venv.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc libmariadb-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -u 10001 app
USER app
EXPOSE 8796
CMD ["python", "manage.py", "mcp", "--host", "0.0.0.0", "--port", "8796"]
