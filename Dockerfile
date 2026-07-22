FROM python:3.12-slim

# tesseract-ocr: system binary pytesseract shells out to (see ocr/tesseract_provider.py)
# libpq-dev/gcc: build deps for psycopg when installing the [postgres] extra
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY migrations/ migrations/
COPY alembic.ini .

RUN pip install --no-cache-dir -e ".[postgres]"

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn pospay.main:app --host 0.0.0.0 --port 8000"]
