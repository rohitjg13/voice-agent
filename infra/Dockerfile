FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy package metadata + source for setuptools' find()
COPY pyproject.toml ./
COPY orchestrator ./orchestrator
COPY packs ./packs
COPY simulator ./simulator

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir .

# Don't run the service as root
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080

# --proxy-headers: trust X-Forwarded-* from Fly's edge so logs carry real client IPs
CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
