FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYDANTIC_AI_NO_BANNER=1

WORKDIR /app

COPY requirements.txt pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home app && mkdir -p logs data && chown app logs
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "cinedata_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
