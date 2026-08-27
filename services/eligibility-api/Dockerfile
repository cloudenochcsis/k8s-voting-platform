FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
# Numeric UID: with runAsNonRoot the kubelet refuses a named USER it cannot verify.
RUN useradd --system --no-create-home --uid 10001 app
USER 10001
EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
