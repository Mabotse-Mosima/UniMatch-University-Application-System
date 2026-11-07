FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ src/
COPY pyproject.toml .
COPY alembic.ini .
COPY migrations/ migrations/

# Install the package
RUN pip install -e . --no-deps

EXPOSE 8000

CMD ["uvicorn", "unimatch.main:app", "--host", "0.0.0.0", "--port", "8000"]
