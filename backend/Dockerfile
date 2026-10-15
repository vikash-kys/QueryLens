FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home appuser
COPY app ./app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=7s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/ready', timeout=6)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
