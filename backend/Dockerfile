FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
# One worker per container keeps the per-conversation AI lock effective;
# scale with more containers behind a load balancer instead of more workers.
# No --proxy-headers: set TRUSTED_PROXY_HOPS to the number of proxies in front (see app/netutil.py).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
