FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN useradd --system --home /app --uid 10001 appuser && mkdir -p /data && chown appuser:appuser /data
COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src
RUN pip install --no-cache-dir .
USER appuser
EXPOSE 80
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1/health', timeout=3).read()"
CMD ["virtual-smart-meter-ecoflow"]
