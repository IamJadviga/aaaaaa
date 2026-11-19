FROM python:3.12-slim

WORKDIR /app

COPY aaa.py .
RUN useradd --create-home --uid 10004 appuser && \
    mkdir -p /data && \
    chmod 777 /data && \
    chown -R appuser:appuser /app
    
USER appuser

ENV PORT=8004
ENV MESSAGE="Hello from Docker"

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" || exit 1


CMD ["python", "aaa.py"]