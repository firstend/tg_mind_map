FROM python:3.12-slim

WORKDIR /app

# Системные зависимости: libpq5 для psycopg2, nodejs/npm для MCP servers
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# MCP servers (Python-based)
RUN pip install --no-cache-dir mcp-server-fetch mcp-server-time

COPY . .

# По умолчанию — gateway; CMD переопределяется в docker-compose
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
