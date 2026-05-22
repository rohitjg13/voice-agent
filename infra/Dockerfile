FROM python:3.11-slim

WORKDIR /app

# Copy package metadata + source for setuptools' find()
COPY pyproject.toml ./
COPY orchestrator ./orchestrator
COPY packs ./packs
COPY simulator ./simulator

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir .

EXPOSE 8080

CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8080"]
