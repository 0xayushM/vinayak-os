FROM python:3.11-slim

WORKDIR /app

# Install system deps needed by psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
 && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY vinayak/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the vinayak package (Python source only, no node_modules/apps/etc.)
COPY vinayak/ ./vinayak/

# Railway / Fly / Render inject PORT at runtime
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn vinayak.api.main:app --host 0.0.0.0 --port $PORT"]
