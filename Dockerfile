FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV LOG_LEVEL=INFO DEFAULT_TIMEOUT=5 MAX_TIMEOUT=30

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request, sys, socket; socket.setdefaulttimeout(2); r=urllib.request.urlopen('http://127.0.0.1:8000/api/healthz'); sys.exit(0 if r.status==200 else 1)" || exit 1
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]